-- Merge rate by author_class x size bucket. Dedup PRs by (repo, pr_number).
with dedup as (
    select distinct on (repo, pr_number)
           repo, pr_number, author_class, merged, size_lines
    from {{ source('silver','gh_pr_outcomes') }}
),
bucketed as (
    select author_class,
           case when size_lines < 20 then '0-20'
                when size_lines < 100 then '20-100'
                when size_lines < 500 then '100-500'
                else '500+' end as size_bucket,
           merged::int as merged
    from dedup
)
select size_bucket, author_class,
       count(*) as n_prs,
       round(avg(merged)::numeric,4) as merged_rate
from bucketed
group by size_bucket, author_class
order by size_bucket, author_class
