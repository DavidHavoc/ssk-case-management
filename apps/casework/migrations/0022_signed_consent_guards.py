from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
            CREATE FUNCTION ssk_signed_consent_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Signed consent evidence is immutable'; END $$;
            CREATE TRIGGER signed_consent_guard BEFORE UPDATE OR DELETE ON casework_signedconsent
            FOR EACH ROW EXECUTE FUNCTION ssk_signed_consent_guard();
            CREATE TRIGGER signed_consent_attachment_guard BEFORE UPDATE OR DELETE ON casework_privateattachment
            FOR EACH ROW WHEN (OLD.parent_type='signed_consent')
            EXECUTE FUNCTION ssk_signed_consent_guard();
        """)
    elif schema_editor.connection.vendor == "sqlite":
        # Development flush uses SQL DELETE. Normal ORM deletion is blocked by pre_delete.
        schema_editor.execute("""
            CREATE TRIGGER signed_consent_update BEFORE UPDATE ON casework_signedconsent BEGIN
            SELECT RAISE(ABORT, 'Signed consent evidence is immutable'); END;
        """)
        schema_editor.execute("""
            CREATE TRIGGER signed_consent_attachment_update BEFORE UPDATE ON casework_privateattachment
            WHEN OLD.parent_type='signed_consent' BEGIN
            SELECT RAISE(ABORT, 'Signed consent evidence is immutable'); END;
        """)


def uninstall(apps, schema_editor):
    alias = schema_editor.connection.alias
    if apps.get_model("casework", "SignedConsent").objects.using(alias).exists():
        raise RuntimeError("Signed consent evidence exists. Preserve its schema and files before reviewing rollback.")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TRIGGER signed_consent_guard ON casework_signedconsent")
        schema_editor.execute("DROP TRIGGER signed_consent_attachment_guard ON casework_privateattachment")
        schema_editor.execute("DROP FUNCTION ssk_signed_consent_guard()")
    elif schema_editor.connection.vendor == "sqlite":
        schema_editor.execute("DROP TRIGGER signed_consent_update")
        schema_editor.execute("DROP TRIGGER signed_consent_attachment_update")


class Migration(migrations.Migration):
    dependencies = [("casework", "0021_signed_consent_file_uniqueness")]
    operations = [migrations.RunPython(install, uninstall)]
