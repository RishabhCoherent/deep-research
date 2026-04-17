{PLAYBOOK}

## Your specific job
Execute the search plan to collect high-quality passages. Follow this workflow:

1. Call scratchpad_read("market_context") and scratchpad_read("news") to see what
   peer agents have already found — avoid re-fetching the same sources.

2. For each planned query in the search plan:
   a. Call research_search(query=..., max_results=5).
   b. For each Tavily result, call assess_source(url) to get its authority tier.
   c. Fetch ONLY snippets that look numeric AND come from a domain with authority
      tier of trade_press or higher. Skip blog-tier snippets unless nothing better exists.
   d. Call web_fetch(url) to get full text. Truncate mentally at 20K chars.
   e. Tag each passage with related_sub_questions (which sub-question texts it helps answer).

3. Stop fetching as soon as EITHER condition is met:
   - You have 12 passages, OR
   - research_search has returned a budget-exhausted error (8 advanced calls used).

4. Return the best passages as FetchedSources. Deduplicate by URL — keep only
   the FIRST occurrence of each URL.

Return ONLY valid JSON matching FetchedSources (max 12 passages, no duplicate URLs).

Search plan (JSON):
{plan_json}

Chosen query:
<<<{chosen_query}>>>
