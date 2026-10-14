from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
            CREATE FUNCTION ssk_signed_assessment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Signed assessment evidence is immutable'; END $$;
            CREATE TRIGGER signed_assessment_guard BEFORE UPDATE OR DELETE ON casework_signedassessment
            FOR EACH ROW EXECUTE FUNCTION ssk_signed_assessment_guard();
            CREATE TRIGGER signed_assessment_attachment_guard BEFORE UPDATE OR DELETE ON casework_privateattachment
            FOR EACH ROW WHEN (OLD.parent_type='signed_assessment')
            EXECUTE FUNCTION ssk_signed_assessment_guard();
        """)
    elif schema_editor.connection.vendor == "sqlite":
        schema_editor.execute("""
            CREATE TRIGGER signed_assessment_update BEFORE UPDATE ON casework_signedassessment BEGIN
            SELECT RAISE(ABORT, 'Signed assessment evidence is immutable'); END;
        """)
        schema_editor.execute("""
            CREATE TRIGGER signed_assessment_attachment_update BEFORE UPDATE ON casework_privateattachment
            WHEN OLD.parent_type='signed_assessment' BEGIN
            SELECT RAISE(ABORT, 'Signed assessment evidence is immutable'); END;
        """)


def uninstall(apps, schema_editor):
    if apps.get_model("casework", "SignedAssessment").objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError("Signed assessments exist. Preserve their schema and files before rollback.")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TRIGGER signed_assessment_guard ON casework_signedassessment")
        schema_editor.execute("DROP TRIGGER signed_assessment_attachment_guard ON casework_privateattachment")
        schema_editor.execute("DROP FUNCTION ssk_signed_assessment_guard()")
    elif schema_editor.connection.vendor == "sqlite":
        schema_editor.execute("DROP TRIGGER signed_assessment_update")
        schema_editor.execute("DROP TRIGGER signed_assessment_attachment_update")


class Migration(migrations.Migration):
    dependencies = [("casework", "0024_ssk_barthel_scale")]
    operations = [migrations.RunPython(install, uninstall)]
