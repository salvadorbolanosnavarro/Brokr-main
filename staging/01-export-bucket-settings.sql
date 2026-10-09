-- READ ONLY production query. Returns SQL to run ONLY in the clean staging DB.
-- Copies bucket configuration, never files or customer objects.
select coalesce(string_agg(format(
 'insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values (%L,%L,%L,%L,%L::text[]) on conflict(id) do nothing;',
 id,name,public,file_size_limit,allowed_mime_types),E'\n'),'-- No buckets') as staging_bucket_sql
from storage.buckets;
