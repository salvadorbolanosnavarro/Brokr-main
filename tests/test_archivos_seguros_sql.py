"""Migraciones 20261106-archivos-*.sql: aplican, protegen y se revierten sin rastro.

Necesita un Postgres local; se salta si no hay. Para correrla:
    BROQUER_TEST_PG="-h /ruta/al/socket -p 5432 -U postgres" python -m unittest tests.test_archivos_seguros_sql
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql-manual"
PSQL = shutil.which("psql")
CONN = os.environ.get("BROQUER_TEST_PG", "")


@unittest.skipUnless(PSQL and CONN, "sin Postgres local (BROQUER_TEST_PG)")
class ArchivosSegurosSQLTests(unittest.TestCase):
    def setUp(self):
        self.db = "t_archivos_" + uuid.uuid4().hex[:8]
        self._psql(["-c", f"create database {self.db}"], db="postgres")
        self._psql(["-f", str(ROOT / "tests/sql/storage_archivos_stub.sql")])

    def tearDown(self):
        self._psql(["-c", f"drop database if exists {self.db}"], db="postgres")

    def _psql(self, args, db=None, ok=True, sql_input=None):
        cmd = [PSQL, *shlex.split(CONN), "-v", "ON_ERROR_STOP=1", "-q", "-tA", "-d", db or self.db, *args]
        p = subprocess.run(cmd, capture_output=True, text=True, input=sql_input, timeout=60)
        if ok:
            self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def _q(self, sql):
        return self._psql(["-c", sql]).stdout.strip()

    def _foto(self):
        return "\n".join([
            self._q("select pg_get_viewdef('public.propiedades_publicas_extra'::regclass, false)"),
            self._q("select id, public, allowed_mime_types, file_size_limit from storage.buckets order by id"),
            self._q("select policyname, permissive, cmd from pg_policies where schemaname='storage' order by 1"),
        ])

    def _sube(self, bucket, nombre):
        r = self._psql([], ok=False, sql_input=(
            "begin; set local role authenticated;"
            " set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';"
            f" insert into storage.objects (bucket_id, name) values ('{bucket}', '{nombre}'); rollback;"))
        return r.returncode == 0

    def test_parte_a_protege_y_se_revierte(self):
        antes = self._foto()
        self._psql(["-f", str(SQL / "20261106-archivos-seguros.sql")])

        self.assertFalse(self._sube("adjuntos-historial", "WhatsApp.html"))
        self.assertFalse(self._sube("fotos-propiedades", "foto.jpg.html"))
        self.assertFalse(self._sube("fotos-propiedades", "logo.svg"))
        self.assertFalse(self._sube("documentos-publicos", "org/x.docx"))
        self.assertTrue(self._sube("fotos-propiedades", "prop_abc.JPG"))
        self.assertTrue(self._sube("documentos-publicos", "org/plano.pdf"))
        self.assertTrue(self._sube("adjuntos-historial", "abc.docx"))

        tipos = self._q("select allowed_mime_types from storage.buckets where id = 'adjuntos-historial'")
        self.assertNotIn("text/html", tipos)
        self.assertNotIn("svg", tipos)
        # Vista pública: el documento privado desaparece; el viejo sin marca sigue.
        nombres = self._q("select jsonb_path_query_array(documentos, '$[*].nombre') "
                          "from public.propiedades_publicas_extra")
        self.assertEqual(nombres, '["viejo.pdf", "publicado.pdf"]')
        self.assertEqual(self._q("select reloptions from pg_class where relname='propiedades_publicas_extra'"),
                         "{security_barrier=true}")
        # Repetirla sin reversa se niega (no pisa el respaldo).
        self.assertNotEqual(self._psql(["-f", str(SQL / "20261106-archivos-seguros.sql")], ok=False).returncode, 0)

        self._psql(["-f", str(SQL / "20261106-archivos-seguros-REVERSA.sql")])
        self.assertEqual(self._foto(), antes)

    def test_parte_b_privatiza_y_se_revierte(self):
        antes = self._foto()
        self._psql(["-f", str(SQL / "20261106-archivos-privados.sql")])
        self.assertEqual(self._q("select string_agg(id || '=' || public, ',' order by id) from storage.buckets "
                                 "where id in ('adjuntos-historial', 'wa-media')"),
                         "adjuntos-historial=false,wa-media=false")
        self._psql(["-f", str(SQL / "20261106-archivos-privados-REVERSA.sql")])
        self.assertEqual(self._foto(), antes)

    def test_verificacion_es_solo_lectura(self):
        antes = self._foto()
        salida = self._psql(["-f", str(SQL / "20261106-archivos-seguros-verificar.sql")]).stdout
        self.assertIn("PENDIENTE", salida)
        self.assertEqual(self._foto(), antes)


if __name__ == "__main__":
    unittest.main()
