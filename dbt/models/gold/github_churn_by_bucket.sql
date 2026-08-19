-- Follow-up churn by author_class x size bucket (of the original change).
with bucketed as (
    select author_class,
           case when churn < 20 then '0-20'
                when churn < 100 then '20-100'
                when churn < 500 then '100-500'
                else '500+' end as size_bucket,
           followup_churn
    from {{ source('silver','gh_churn_events') }}
)
select size_bucket, author_class,
       count(*) as n,
       round(avg(followup_churn)::numeric,1) as mean_followup,
       percentile_cont(0.5) within group (order by followup_churn) as median_followup
from bucketed
group by size_bucket, author_class
order by size_bucket, author_class
