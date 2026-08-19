-- AI-adoption share by year. AI signal = coauthor_ai OR ai_agent (clean).
-- Dedup AI commits by sha, then numerator/denominator per year.
with ai as (
    select distinct sha, month
    from {{ source('silver','gh_matches') }}
    where coalesce(coauthor_ai,false) or coalesce(ai_agent,false)
),
ai_by_month as (select month, count(*) as n_ai from ai group by month),
joined as (
    select t.month, t.n_commits, coalesce(a.n_ai,0) as n_ai_commits,
           left(t.month,4) as year
    from {{ source('silver','gh_totals') }} t
    left join ai_by_month a using (month)
)
select year,
       sum(n_ai_commits) as n_ai_commits,
       sum(n_commits)    as n_commits,
       round(100.0*sum(n_ai_commits)/nullif(sum(n_commits),0),4) as ai_share_pct
from joined group by year order by year
