"""
ContentEngine — orchestrates all content generation for the report.

For each SectionPlan:
1. Generate data insights from ME numbers (fast, no LLM)
2. Run web research for real-world context + citations
3. Write content using LLM with section-specific prompts
"""

from __future__ import annotations
import asyncio
import logging
import re

from report.mapper import (
    SectionPlan, get_me_for_dimension, get_total_data,
    get_all_years, get_cagr_key, get_snapshot_years,
)
from report.content.citations import CitationManager
from report.content.research import (
    research_topic, research_company, research_region,
    research_queries, build_research_context,
)
from report.content.writer import write_section, write_light, write_batch, compress_insights_for_sidebar
from report.content.data_insights import (
    generate_total_insights, generate_segment_insights,
    generate_dimension_summary, generate_regional_insights,
)
from report.content import prompts

logger = logging.getLogger(__name__)


class ContentEngine:
    """Generates all narrative content for the report."""

    def __init__(self, topic: str, plans: list[SectionPlan],
                 me_data: dict, toc: dict):
        self.topic = topic
        self.plans = plans
        self.me_data = me_data
        self.me_global = me_data.get("global", {})
        self.toc = toc
        self.citations = CitationManager()

        self.years = get_all_years(self.me_global)
        self.cagr_key = get_cagr_key(self.me_global)
        self.snapshot_yrs = get_snapshot_years(self.years)

        self.vol_unit = self.me_global.get("market_volume", {}).get("unit", "")
        self.val_unit = self.me_global.get("market_value", {}).get("unit", "")

    async def generate_all(self, progress_callback=None) -> dict[int, dict]:
        """Generate content for all sections.

        Returns: {section_number: content_dict}
        """
        content_store = {}

        for plan in sorted(self.plans, key=lambda p: p.section_number):
            if progress_callback:
                progress_callback(f"Generating content: S{plan.section_number} ({plan.section_type})")

            try:
                content = await self._generate_section(plan)
                if content:
                    content_store[plan.section_number] = content
                    logger.info(f"  S{plan.section_number} content generated ({len(str(content))} chars)")
            except Exception as e:
                logger.error(f"  S{plan.section_number} content generation failed: {e}")
                content_store[plan.section_number] = {}

        logger.info(f"Content generation complete. {self.citations.count} citations collected.")
        return content_store

    async def _generate_section(self, plan: SectionPlan) -> dict:
        """Route to appropriate generator based on section_type."""
        generators = {
            "overview": self._gen_overview,
            "key_insights": self._gen_key_insights,
            "segment": self._gen_segment,
            "region": self._gen_regional,
            "competitive": self._gen_competitive,
            "appendix": self._gen_appendix,
        }
        gen = generators.get(plan.section_type, self._gen_appendix)
        return await gen(plan)

    # ─── Overview (S2) ───────────────────────────────────────────────────

    async def _gen_overview(self, plan: SectionPlan) -> dict:
        """Generate Market Overview + Executive Summary content."""
        total = get_total_data(self.me_global)
        total_insights = generate_total_insights(
            total, self.years, self.cagr_key, self.vol_unit, self.val_unit,
        )

        # Research the overall market
        results = await research_topic(
            self.topic,
            ["market overview definition scope",
             "market size growth forecast",
             "key drivers trends",
             "industry landscape applications"],
            self.citations, section_id="overview",
        )
        research_ctx = build_research_context(results)
        citation_table = self.citations.get_citation_table("overview")

        # Market Definition
        market_def = await write_section(
            prompts.OVERVIEW_DEFINITION.format(
                topic=self.topic,
                research_context=research_ctx,
                data_insights="\n".join(total_insights),
                citation_table=citation_table,
            ),
        )

        # Executive Summaries per dimension
        exec_summaries = {}
        segment_plans = [p for p in self.plans if p.section_type == "segment"]
        for sp in segment_plans:
            dim_data = get_me_for_dimension(self.me_global, sp.dimension_key)
            vol_items = dim_data.get("volume", {})
            dim_insights = generate_segment_insights(
                sp.dimension_name, vol_items, self.years, self.cagr_key, self.vol_unit,
            )
            all_dim_insights = []
            for item_insights in dim_insights.values():
                all_dim_insights.extend(item_insights[:2])

            summary = await write_light(
                prompts.OVERVIEW_EXEC_SUMMARY.format(
                    topic=self.topic,
                    dimension_name=sp.dimension_name,
                    data_insights="\n".join(all_dim_insights),
                    segment_names=", ".join(sp.segment_names),
                    research_context=research_ctx[:2000],
                    citation_table=citation_table,
                ),
            )
            exec_summaries[sp.dimension_name] = summary

        # Market Scenario
        scenario = await write_light(
            prompts.OVERVIEW_SCENARIO.format(
                topic=self.topic,
                data_insights="\n".join(total_insights),
            ),
        )

        # Split insights by type (generate_total_insights produces volume then value)
        vol_insights = [i for i in total_insights if "volume" in i.lower()][:3]
        val_insights = [i for i in total_insights if "value" in i.lower()][:3]

        # Compress both sets to ≤90 chars each for sidebar display
        sidebar_insights_vol, sidebar_insights_val = await asyncio.gather(
            compress_insights_for_sidebar(vol_insights),
            compress_insights_for_sidebar(val_insights),
        )

        return {
            "market_definition": market_def,
            "exec_summaries": exec_summaries,
            "market_scenario": scenario,
            "data_insights": total_insights,
            "sidebar_insights": sidebar_insights_vol,
            "sidebar_insights_value": sidebar_insights_val,
        }

    # ─── Key Insights (S3) ───────────────────────────────────────────────

    async def _gen_key_insights(self, plan: SectionPlan) -> dict:
        """Generate content for all Key Insights subsections."""
        subsections_content = {}

        # Pre-compute enriched data insights (total + segment breakdowns)
        total = get_total_data(self.me_global)
        total_insights = generate_total_insights(
            total, self.years, self.cagr_key, self.vol_unit, self.val_unit,
        )
        segment_summaries = self._build_segment_summaries()
        enriched_insights = total_insights + segment_summaries

        # Get segment names for options/attractiveness prompts
        segment_plans = [p for p in self.plans if p.section_type == "segment"]
        all_segments = []
        for sp in segment_plans:
            all_segments.extend(sp.segment_names)

        for sub in plan.subsections:
            title = sub.get("title", "")
            if not title:
                continue

            template = self._match_key_insight_template(title)
            if not template:
                continue

            sid = re.sub(r'[^a-z0-9]+', '_', title.lower())[:20]

            # Research this subsection
            queries = [
                f"{self.topic} {title}",
                f"{self.topic} {title} analysis trends",
            ]
            results = await research_queries(
                queries, self.citations, section_id=sid, scrape_top=1,
            )
            research_ctx = build_research_context(results)
            citation_table = self.citations.get_citation_table(sid)

            text = await write_section(
                template.format(
                    topic=self.topic,
                    research_context=research_ctx,
                    data_insights="\n".join(enriched_insights),
                    citation_table=citation_table,
                    segment_names=", ".join(all_segments[:10]),
                ),
            )

            # Parse structured data blocks from LLM response
            structured = _parse_structured_blocks(title, text)

            subsections_content[title] = {
                "text": text,
                "children": sub.get("children", []),
                "structured": structured,
            }

        return {"subsections": subsections_content}

    def _build_segment_summaries(self) -> list[str]:
        """Build segment-level summary lines for enriched data context."""
        summaries = []
        last_yr = self.years[-1] if self.years else ""
        if not last_yr:
            return summaries

        vol_section = self.me_global.get("market_volume", {})
        for dim_key, items in vol_section.items():
            if dim_key in ("unit",) or not isinstance(items, dict) or not items:
                continue
            dim_name = dim_key.replace("by_", "").replace("_", " ").title()

            sized = []
            for name, data in items.items():
                val = data.get("forecast", {}).get(last_yr, 0)
                cagr = data.get(self.cagr_key, 0)
                try:
                    sized.append((name, float(val), float(cagr) * 100))
                except (ValueError, TypeError):
                    continue

            if not sized:
                continue

            largest = max(sized, key=lambda x: x[1])
            fastest = max(sized, key=lambda x: x[2])
            summaries.append(
                f"By {dim_name}: {largest[0]} holds the largest market position, "
                f"while {fastest[0]} is the fastest growing at {fastest[2]:.1f}% CAGR."
            )

        return summaries

    def _match_key_insight_template(self, title: str) -> str | None:
        """Find the best prompt template for a Key Insights subsection title."""
        title_lower = title.lower()
        for keyword, template in prompts.KEY_INSIGHTS_MAP.items():
            if keyword in title_lower:
                return template
        # Default to trends template for unmatched subsections
        return prompts.KEY_INSIGHTS_TRENDS

    # ─── Segment (S4-S8) ────────────────────────────────────────────────

    async def _gen_segment(self, plan: SectionPlan) -> dict:
        """Generate content for a segment analysis section."""
        dim_key = plan.dimension_key
        dim_name = plan.dimension_name
        dim_data = get_me_for_dimension(self.me_global, dim_key)
        vol_items = dim_data.get("volume", {})
        val_items = dim_data.get("value", {})
        items = vol_items or val_items

        # Data insights for all items
        item_insights = generate_segment_insights(
            dim_name, items, self.years, self.cagr_key,
            self.vol_unit if vol_items else self.val_unit,
        )
        summary = generate_dimension_summary(dim_name, items, self.years, self.cagr_key)

        # Research the dimension
        sid = f"seg_{dim_key[:10]}"
        results = await research_topic(
            self.topic,
            [f"by {dim_name} segment analysis",
             f"{dim_name} market trends drivers"],
            self.citations, section_id=sid,
        )
        research_ctx = build_research_context(results)
        citation_table = self.citations.get_citation_table(sid)

        # Dimension overview
        all_data_insights = [summary] if summary else []
        for item_name, insights in item_insights.items():
            all_data_insights.extend(insights[:1])

        overview = await write_section(
            prompts.SEGMENT_OVERVIEW.format(
                topic=self.topic,
                dimension_name=dim_name,
                segment_names=", ".join(plan.segment_names),
                data_insights="\n".join(all_data_insights),
                research_context=research_ctx,
                citation_table=citation_table,
            ),
        )

        # Per-item analysis
        items_content = {}
        for item_name in plan.segment_names:
            item_data_insights = item_insights.get(item_name, [])

            # Research individual item
            item_sid = f"seg_{item_name[:8]}"
            item_results = await research_queries(
                [f"{self.topic} {item_name} market"],
                self.citations, section_id=item_sid, scrape_top=0,
            )
            item_research = build_research_context(item_results, max_chars=3000)
            item_citations = self.citations.get_citation_table(item_sid)

            item_text = await write_section(
                prompts.SEGMENT_ITEM.format(
                    topic=self.topic,
                    dimension_name=dim_name,
                    item_name=item_name,
                    data_insights="\n".join(item_data_insights),
                    research_context=item_research or research_ctx[:2000],
                    citation_table=item_citations or citation_table,
                ),
            )

            items_content[item_name] = {
                "analysis": item_text,
                "data_insights": item_data_insights,
            }

        return {
            "dimension_overview": overview,
            "items": items_content,
            "comparison_narrative": summary,
        }

    # ─── Regional (S9) ──────────────────────────────────────────────────

    async def _gen_regional(self, plan: SectionPlan) -> dict:
        """Generate content for the regional analysis section."""
        # Regional data from global by_region
        vol_section = self.me_global.get("market_volume", {})
        val_section = self.me_global.get("market_value", {})
        region_val = val_section.get("by_region", {})

        region_insights = generate_regional_insights(
            region_val, self.years, self.cagr_key, self.val_unit,
        )

        # Cross-region research
        results = await research_topic(
            self.topic,
            ["regional market analysis global",
             "regional growth drivers comparison"],
            self.citations, section_id="regional",
        )
        research_ctx = build_research_context(results)
        citation_table = self.citations.get_citation_table("regional")

        region_names = [r.get("name", "") for r in plan.regions]
        all_region_insights = []
        for name, insights in region_insights.items():
            all_region_insights.extend(insights)

        # Cross-region overview
        overview = await write_section(
            prompts.REGIONAL_OVERVIEW.format(
                topic=self.topic,
                data_insights="\n".join(all_region_insights),
                region_names=", ".join(region_names),
                research_context=research_ctx,
                citation_table=citation_table,
            ),
        )

        # Per-region content
        regions_content = {}
        for region_info in plan.regions:
            region_name = region_info.get("name", "")
            countries = region_info.get("countries", [])
            r_insights = region_insights.get(region_name, [])

            # Research this region
            r_sid = f"reg_{region_name[:6]}"
            r_results = await research_region(
                region_name, self.topic, self.citations, section_id=r_sid,
            )
            r_research = build_research_context(r_results, max_chars=3000)
            r_citations = self.citations.get_citation_table(r_sid)

            region_text = await write_section(
                prompts.REGION_DETAIL.format(
                    topic=self.topic,
                    region_name=region_name,
                    data_insights="\n".join(r_insights),
                    countries=", ".join(countries),
                    research_context=r_research or research_ctx[:2000],
                    citation_table=r_citations or citation_table,
                ),
            )

            # Country insights (batched)
            country_content = {}
            if countries:
                country_text = await write_light(
                    prompts.COUNTRY_BATCH.format(
                        topic=self.topic,
                        region_name=region_name,
                        country_names=", ".join(countries),
                        research_context=r_research or research_ctx[:2000],
                        citation_table=r_citations or citation_table,
                    ),
                )
                country_content = _parse_country_sections(country_text, countries)

            regions_content[region_name] = {
                "overview": region_text,
                "countries": country_content,
            }

        return {
            "cross_region_overview": overview,
            "regions": regions_content,
        }

    # ─── Competitive (S10) ──────────────────────────────────────────────

    async def _gen_competitive(self, plan: SectionPlan) -> dict:
        """Generate competitive landscape content."""
        all_companies = []
        for group, companies in plan.companies.items():
            all_companies.extend(companies)

        # Research competitive landscape
        results = await research_topic(
            self.topic,
            ["competitive landscape key players market share",
             "industry competition analysis"],
            self.citations, section_id="competitive",
        )
        research_ctx = build_research_context(results)
        citation_table = self.citations.get_citation_table("competitive")

        # Overview
        overview = await write_section(
            prompts.COMPETITIVE_OVERVIEW.format(
                topic=self.topic,
                company_names=", ".join(all_companies[:15]),
                research_context=research_ctx,
                citation_table=citation_table,
            ),
        )

        # Company profiles in batches
        companies_content = {}
        batch_size = 5
        for i in range(0, len(all_companies), batch_size):
            batch = all_companies[i:i + batch_size]

            # Research this batch
            for company in batch:
                c_results = await research_company(
                    company, self.topic, self.citations, section_id="com",
                )

            c_citation_table = self.citations.get_citation_table("com")
            c_research = build_research_context(c_results, max_chars=4000)

            batch_text = await write_section(
                prompts.COMPANY_PROFILE_BATCH.format(
                    topic=self.topic,
                    company_names=", ".join(batch),
                    research_context=c_research or research_ctx[:3000],
                    citation_table=c_citation_table or citation_table,
                ),
            )

            parsed = _parse_company_sections(batch_text, batch)
            companies_content.update(parsed)

        return {
            "landscape_overview": overview,
            "companies": companies_content,
            "positioning_narrative": "",
        }

    # ─── Appendix (S1, S11, S12) ────────────────────────────────────────

    async def _gen_appendix(self, plan: SectionPlan) -> dict:
        """Generate appendix section content."""
        total = get_total_data(self.me_global)
        total_insights = generate_total_insights(
            total, self.years, self.cagr_key, self.vol_unit, self.val_unit,
        )
        first_yr = self.years[0] if self.years else ""
        last_yr = self.years[-1] if self.years else ""

        # Gather dimension and region names
        dimensions = []
        regions = []
        for p in self.plans:
            if p.section_type == "segment":
                dimensions.append(p.dimension_name)
            elif p.section_type == "region":
                regions = [r.get("name", "") for r in p.regions]

        market_val = ""
        val_data = total.get("value", {}).get("forecast", {})
        if val_data and last_yr:
            market_val = f"US$ {val_data.get(last_yr, 'N/A')} Million"

        subsections_content = {}

        for sub in plan.subsections:
            title = sub.get("title", "")
            title_lower = title.lower()

            if "objective" in title_lower:
                text = await write_light(prompts.APPENDIX_OBJECTIVES.format(
                    topic=self.topic, first_year=first_yr, last_year=last_yr,
                    dimensions=", ".join(dimensions), regions=", ".join(regions),
                    market_value=market_val,
                ))
            elif "assumption" in title_lower:
                text = await write_light(prompts.APPENDIX_ASSUMPTIONS.format(
                    topic=self.topic, first_year=first_yr, last_year=last_yr,
                ))
            elif "methodology" in title_lower:
                text = await write_light(prompts.APPENDIX_METHODOLOGY.format(
                    topic=self.topic, first_year=first_yr, last_year=last_yr,
                ))
            elif "analyst" in title_lower or "recommendation" in title_lower or "wheel" in title_lower or "view" in title_lower or "opportunity" in title_lower:
                text = await write_light(prompts.APPENDIX_ANALYST.format(
                    topic=self.topic,
                    data_insights="\n".join(total_insights),
                ))
            else:
                text = await write_light(
                    f'Write a brief professional section on "{title}" for a market research '
                    f'report on "{self.topic}". Write 300-500 words.'
                )

            subsections_content[title] = text

        return {"subsections": subsections_content}


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _parse_country_sections(text: str, countries: list[str]) -> dict[str, str]:
    """Parse batch country response into per-country content."""
    result = {}
    for i, country in enumerate(countries):
        pattern = rf'###?\s*{re.escape(country)}(.*?)(?=###?\s*|$)'
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            result[country] = match.group(1).strip()
        else:
            result[country] = ""
    return result


def _parse_company_sections(text: str, companies: list[str]) -> dict[str, str]:
    """Parse batch company response into per-company content."""
    result = {}
    for i, company in enumerate(companies):
        escaped = re.escape(company)
        # Look for ### Company Name or **Company Name**
        pattern = rf'(?:###?\s*{escaped}|\*\*{escaped}\*\*)(.*?)(?=###?\s*|\*\*[A-Z]|\Z)'
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            result[company] = match.group(1).strip()
        else:
            result[company] = ""
    return result


# ─── Structured Block Parsers (Key Insights) ────────────────────────────────


def _parse_structured_blocks(title: str, text: str):
    """Route to the appropriate parser based on subsection title."""
    title_lower = title.lower()
    if "pest" in title_lower:
        return _parse_pest(text)
    if "porter" in title_lower:
        return _parse_porters(text)
    if "dynamic" in title_lower or "impact" in title_lower:
        return _parse_impact(text)
    if "development" in title_lower:
        return _parse_developments(text)
    if "supply" in title_lower and "chain" in title_lower:
        return _parse_supply_chain(text)
    return {}


def _parse_pest(text: str) -> dict:
    """Extract PEST summary from ===PEST_SUMMARY=== block."""
    match = re.search(r'===PEST_SUMMARY===(.*?)===END_PEST===', text, re.DOTALL)
    if not match:
        return {}
    block = match.group(1).strip()
    result = {}
    for category in ("political", "economic", "social", "technological"):
        cat_match = re.search(
            rf'{category}:\s*(.+?)(?=\n(?:political|economic|social|technological):|\Z)',
            block, re.DOTALL | re.IGNORECASE,
        )
        if cat_match:
            result[category] = cat_match.group(1).strip()
    return result


def _parse_porters(text: str) -> dict:
    """Extract Porter's Five Forces ratings from ===PORTERS_SUMMARY=== block."""
    match = re.search(r'===PORTERS_SUMMARY===(.*?)===END_PORTERS===', text, re.DOTALL)
    if not match:
        return {}
    result = {}
    for line in match.group(1).strip().split("\n"):
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 3:
            result[parts[0]] = {"rating": parts[1], "key_factor": parts[2]}
    return result


def _parse_impact(text: str) -> list[dict]:
    """Extract impact analysis items from ===IMPACT_SUMMARY=== block."""
    match = re.search(r'===IMPACT_SUMMARY===(.*?)===END_IMPACT===', text, re.DOTALL)
    if not match:
        return []
    items = []
    for line in match.group(1).strip().split("\n"):
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 4:
            items.append({
                "factor": parts[0], "type": parts[1],
                "impact": parts[2], "horizon": parts[3],
            })
    return items


def _parse_developments(text: str) -> list[dict]:
    """Extract key developments from ===DEVELOPMENTS_SUMMARY=== block."""
    match = re.search(r'===DEVELOPMENTS_SUMMARY===(.*?)===END_DEVELOPMENTS===', text, re.DOTALL)
    if not match:
        return []
    items = []
    for line in match.group(1).strip().split("\n"):
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 3:
            items.append({
                "date": parts[0], "company": parts[1], "description": parts[2],
            })
    return items


def _parse_supply_chain(text: str) -> list[str]:
    """Extract supply chain stages from ===SUPPLY_CHAIN=== block."""
    match = re.search(r'===SUPPLY_CHAIN===(.*?)===END_SUPPLY_CHAIN===', text, re.DOTALL)
    if not match:
        return []
    stages = [s.strip() for s in match.group(1).strip().split("|") if s.strip()]
    return stages if stages else []
