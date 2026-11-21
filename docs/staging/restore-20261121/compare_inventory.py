"""Compare restored snapshot with the live staging inventory, naming time-point differences."""
import json
import gzip
from pathlib import Path
root=Path(__file__).parent
source=json.loads(gzip.decompress((root/'source-inventory.json.gz').read_bytes()))
target=json.loads(gzip.decompress((root/'restored-inventory.json.gz').read_bytes()))

def key(row,fields):return tuple(row.get(k) for k in fields)
def compare(kind,fields,skip=lambda row:False):
 left={key(r,fields):r for r in source.get(kind,[]) if not skip(r)}
 right={key(r,fields):r for r in target.get(kind,[]) if not skip(r)}
 return {'source':len(left),'restored':len(right),'missing':[list(k) for k in left.keys()-right.keys()], 'extra':[list(k) for k in right.keys()-left.keys()], 'changed':[{'key':list(k),'source':left[k],'restored':right[k]} for k in left.keys()&right.keys() if left[k]!=right[k]]}
post_backup_tables={'cecil_staging_pilot','cecil_staging_error_receipts'}
def later(row):return row.get('table_name',row.get('table',row.get('tablename'))) in post_backup_tables
report={'source':'tymhlvawnqadqgwnpruk','restored':'hdpstaqcswrdcrozcxrq','backup_at_utc':'2026-11-21T07:05:17Z','post_backup_tables_excluded':sorted(post_backup_tables)}
for kind,fields in [('tables',('schema_name','table_name')),('columns',('table_schema','table_name','column_name')),('policies',('schemaname','tablename','policyname')),('functions',('schema','name','args')),('triggers',('schema','table','name')),('constraints',('schema','table','name')),('indexes',('schemaname','tablename','indexname')),('rls',('schema','table')),('extensions',('name',)),('roles',('name',))]:
 report[kind]=compare(kind,fields,later)
(root/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
for kind in ('tables','columns','policies','functions','triggers','constraints','indexes','rls','extensions','roles'):
 r=report[kind];print(kind,'source',r['source'],'restored',r['restored'],'missing',len(r['missing']),'extra',len(r['extra']),'changed',len(r['changed']))
