select repo,
       count(*) as touches,
       sum((author_class <> 'human')::int) as ai_touches,
       round(100.0*sum((author_class <> 'human')::int)/count(*),1) as ai_pct
from {{ source('silver','gh_churn_events') }}
group by repo order by ai_pct
