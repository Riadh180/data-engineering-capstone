with ai as (
    select distinct sha, month
    from {{ source('silver','gh_matches') }}
    where coalesce(coauthor_ai,false) or coalesce(ai_agent,false)
),
ai_by_month as (select month, count(*) as n_ai from ai group by month)
select t.month,
       coalesce(a.n_ai,0) as n_ai_commits,
       t.n_commits,
       round(100.0*coalesce(a.n_ai,0)/nullif(t.n_commits,0),4) as ai_share_pct
from {{ source('silver','gh_totals') }} t
left join ai_by_month a using (month)
order by t.month
