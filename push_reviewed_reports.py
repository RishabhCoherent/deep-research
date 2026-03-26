"""Push CEO-reviewed expert reports to the database, updating all layers."""
import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from dotenv import load_dotenv
load_dotenv('.env')

from docx import Document
from history_manager import get_history
from database import SessionLocal, ResearchHistory, init_db

init_db()

# ─── DOCX → Markdown converter ──────────────────────────────────────────────

def docx_to_markdown(filepath):
    """Convert a DOCX file to clean markdown."""
    doc = Document(filepath)
    lines = []
    in_list = False

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            if in_list:
                in_list = False
            lines.append('')
            continue

        style = para.style.name if para.style else ''

        if style == 'Heading 1':
            lines.append(f'## {text}')
            lines.append('')
        elif style == 'Heading 2':
            lines.append(f'### {text}')
            lines.append('')
        elif style == 'Heading 3':
            lines.append(f'#### {text}')
            lines.append('')
        elif 'List' in style or text.startswith('•') or text.startswith('- '):
            # Clean up bullet markers
            clean = text.lstrip('•-– ').strip()
            lines.append(f'- {clean}')
            in_list = True
        else:
            lines.append(text)
            lines.append('')

    # Clean up multiple blank lines
    md = '\n'.join(lines)
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


# ─── Section name mappings ───────────────────────────────────────────────────

# Map old L0/L1 section names → new names for each topic
RARE_EARTH_SECTION_MAP = {
    '## Geopolitical Tensions': '## Geopolitical Control and Supply Disruption',
    '## Supply Chain Vulnerabilities': '## Supply Chain Fragility and Production Bottlenecks',
    '## Critical Rare Earth Elements': '## Structural Role of Rare Earths in EV Production',
    '## Government Policies': '## Government Intervention and Supply Chain Stabilization',
    '## Mitigation Strategies': '## OEM Mitigation Strategies',
    '## Market Pricing Dynamics': '## Cost Escalation and EV Pricing',
}

TAX_SECTION_MAP = {
    '## Rebate Schemes Analysis': '## Rebate Schemes',
    '## Support Initiatives Evaluation': '## Support Initiatives',
    '## Electronics Component Manufacturing Scheme (ECMS) Impact': '## ECMS (Electronics Component Manufacturing Scheme)',
}

AI_CODING_SECTION_MAP = {
    # Section names are the same, no renaming needed
}


def update_layer_sections(content, section_map):
    """Replace section headings in layer content based on mapping."""
    if not section_map:
        return content
    for old, new in section_map.items():
        content = content.replace(old, new)
    return content


# ─── Database update ─────────────────────────────────────────────────────────

def update_report_in_db(history_id, new_expert_md, section_map):
    """Update the expert layer content and rename sections in L0/L1."""
    with SessionLocal() as session:
        row = session.query(ResearchHistory).filter_by(id=history_id).first()
        if not row:
            print(f'  ERROR: Entry {history_id} not found in database!')
            return False

        report = row.report
        layers = report.get('layers', [])

        # Update L0 (baseline) and L1 (enhanced) section headings
        for layer in layers:
            if layer['layer'] in (0, 1) and section_map:
                old_content = layer.get('content', '')
                new_content = update_layer_sections(old_content, section_map)
                if old_content != new_content:
                    layer['content'] = new_content
                    # Update word count
                    layer['word_count'] = len(new_content.split())
                    print(f'  Updated L{layer["layer"]} section headings')
                else:
                    print(f'  L{layer["layer"]} sections unchanged')

            # Update L2 (expert) with new reviewed content
            if layer['layer'] == 2:
                layer['content'] = new_expert_md
                layer['word_count'] = len(new_expert_md.split())
                print(f'  Updated L2 expert content ({layer["word_count"]} words)')

        # Recalculate total_words
        report['layers'] = layers
        row.report = report
        row.total_words = sum(l.get('word_count', 0) for l in layers)

        # Force SQLAlchemy to detect JSONB change
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(row, 'report')

        session.commit()
        print(f'  Committed to database! Total words: {row.total_words}')
        return True


# ─── Main ────────────────────────────────────────────────────────────────────

UPDATES = [
    {
        'name': 'Rare Earth EV Geopolitical Analysis',
        'docx': 'conformedAndReadyToPush/rare_earth_ev_report.docx',
        'history_id': '20260321_173343_analyzing_the_influence_of_geopolitical',
        'section_map': RARE_EARTH_SECTION_MAP,
    },
    {
        'name': 'AI Coding Platforms Sentiment Analysis',
        'docx': 'conformedAndReadyToPush/AI_Coding_Platforms_Sentiment_Analysis.docx',
        'history_id': '20260321_152820_conduct_a_sentiment_analysis_of_ai_codin',
        'section_map': AI_CODING_SECTION_MAP,
    },
    {
        'name': 'Tax Implications India Electronics',
        'docx': 'conformedAndReadyToPush/combined_tax_report.docx',
        'history_id': '20260321_143922_a_detailed_analysis_of_the_tax_implicati',
        'section_map': TAX_SECTION_MAP,
    },
]

if __name__ == '__main__':
    for update in UPDATES:
        print(f'\n{"="*60}')
        print(f'Processing: {update["name"]}')
        print(f'{"="*60}')

        # Convert DOCX to markdown
        md = docx_to_markdown(update['docx'])
        print(f'  Converted DOCX → {len(md.split())} words of markdown')

        # Preview first few lines
        preview = '\n'.join(md.split('\n')[:5])
        print(f'  Preview:\n    {preview[:200]}...')

        # Update database
        success = update_report_in_db(
            update['history_id'],
            md,
            update['section_map'],
        )

        if success:
            print(f'  ✓ Done!')
        else:
            print(f'  ✗ Failed!')

    print(f'\n{"="*60}')
    print('All updates complete!')