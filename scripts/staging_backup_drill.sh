#!/usr/bin/env bash
# Full database drill only against staging and an explicitly disposable target.
# Supply libpq service definitions and passwords privately, never in git/argv.
set -euo pipefail
umask 077
stage_ref=tymhlvawnqadqgwnpruk
source_service=${STAGING_SOURCE_SERVICE:-}
target_service=${STAGING_RESTORE_SERVICE:-}
artifact_dir=${STAGING_BACKUP_DIR:-}
if [[ -z "$source_service" || -z "$target_service" || -z "$artifact_dir" || "$source_service" == "$target_service" ]]; then
  echo 'Need two distinct private libpq services and a private backup directory.' >&2; exit 2
fi
for executable in pg_dump pg_dumpall pg_restore psql python3; do
  command -v "$executable" >/dev/null || { echo "Missing tool: $executable" >&2; exit 2; }
done
# Inspect connection metadata without printing passwords. Source must be staging;
# destination must be explicitly marked disposable and cannot be the live staging DB.
python3 - "$source_service" "$target_service" "$stage_ref" <<'PY'
import configparser,os,sys
from pathlib import Path
p=Path(os.environ.get('PGSERVICEFILE',str(Path.home()/'.pg_service.conf')))
c=configparser.ConfigParser();c.read(p)
src,dst,ref=sys.argv[1:]
assert src in c and dst in c,'Missing private libpq service'
for name in (src,dst):
 v=' '.join(c[name].values())
 assert 'urtgysmtnvoqaljuhntz' not in v,'Production is forbidden in this drill'
assert ref in ' '.join(c[src].values()),'Source is not staging'
assert c[dst].get('application_name')=='cecil-disposable-restore','Destination must be disposable'
assert ref not in ' '.join(c[dst].values()),'Never restore over live staging'
PY
mkdir -p "$artifact_dir"
started=$(date +%s)
pg_dump "service=$source_service" --format=custom --file "$artifact_dir/database.dump"
pg_dumpall --database="service=$source_service" --roles-only --no-role-passwords > "$artifact_dir/roles.sql"
backup_finished=$(date +%s)
pg_restore --list "$artifact_dir/database.dump" > "$artifact_dir/contents.txt"
# A compatible, isolated Supabase/Postgres destination is a prerequisite. Roles,
# required extensions, auth/storage schemas and service settings must be prepared.
# Fail on first restore error; never clean/drop an existing database implicitly.
pg_restore --dbname="service=$target_service" --exit-on-error --single-transaction "$artifact_dir/database.dump"
restore_finished=$(date +%s)
python3 - "$artifact_dir" "$started" "$backup_finished" "$restore_finished" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]);a,b,c=map(int,sys.argv[2:]);f=p/'database.dump'
(p/'timing.json').write_text(json.dumps({'backup_seconds':b-a,'restore_seconds':c-b,'total_seconds':c-a,'dump_bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'verification':'PENDING counts, RLS, function signatures, files and login'},indent=2))
PY
echo 'Restore completed. Timings are private; functional/content verification is still required.'
