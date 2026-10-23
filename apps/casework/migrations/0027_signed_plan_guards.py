from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
            CREATE FUNCTION ssk_signed_plan_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Signed plan evidence is immutable'; END $$;
            CREATE TRIGGER signed_plan_guard BEFORE UPDATE OR DELETE ON casework_signedplan
            FOR EACH ROW EXECUTE FUNCTION ssk_signed_plan_guard();
            CREATE TRIGGER signed_plan_attachment_guard BEFORE UPDATE OR DELETE ON casework_privateattachment
            FOR EACH ROW WHEN (OLD.parent_type='signed_plan')
            EXECUTE FUNCTION ssk_signed_plan_guard();
            CREATE FUNCTION ssk_plan_content_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF EXISTS (SELECT 1 FROM casework_signedplan WHERE plan_id=OLD.id) THEN
                    RAISE EXCEPTION 'Signed plan content is immutable';
                END IF;
                RETURN NEW;
            END $$;
            CREATE TRIGGER signed_plan_content_guard BEFORE UPDATE ON casework_individualplan
            FOR EACH ROW WHEN (
                (to_jsonb(OLD) - ARRAY['status','updated_at']) IS DISTINCT FROM
                (to_jsonb(NEW) - ARRAY['status','updated_at'])
            ) EXECUTE FUNCTION ssk_plan_content_guard();
        """)
    elif schema_editor.connection.vendor == "sqlite":
        schema_editor.execute("""
            CREATE TRIGGER signed_plan_update BEFORE UPDATE ON casework_signedplan BEGIN
            SELECT RAISE(ABORT, 'Signed plan evidence is immutable'); END;
        """)
        schema_editor.execute("""
            CREATE TRIGGER signed_plan_attachment_update BEFORE UPDATE ON casework_privateattachment
            WHEN OLD.parent_type='signed_plan' BEGIN
            SELECT RAISE(ABORT, 'Signed plan evidence is immutable'); END;
        """)
        fields = [f.column for f in apps.get_model("casework", "IndividualPlan")._meta.concrete_fields
                  if f.name not in {"status", "updated_at"}]
        changed = " OR ".join(f'OLD."{field}" IS NOT NEW."{field}"' for field in fields)
        schema_editor.execute(f"""
            CREATE TRIGGER signed_plan_content_update BEFORE UPDATE ON casework_individualplan
            WHEN ({changed}) AND EXISTS (SELECT 1 FROM casework_signedplan WHERE plan_id=OLD.id) BEGIN
            SELECT RAISE(ABORT, 'Signed plan content is immutable'); END;
        """)


def uninstall(apps, schema_editor):
    if apps.get_model("casework", "SignedPlan").objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError("Signed plans exist. Preserve their schema and files before rollback.")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TRIGGER signed_plan_content_guard ON casework_individualplan")
        schema_editor.execute("DROP FUNCTION ssk_plan_content_guard()")
        schema_editor.execute("DROP TRIGGER signed_plan_guard ON casework_signedplan")
        schema_editor.execute("DROP TRIGGER signed_plan_attachment_guard ON casework_privateattachment")
        schema_editor.execute("DROP FUNCTION ssk_signed_plan_guard()")
    elif schema_editor.connection.vendor == "sqlite":
        for name in ("signed_plan_update", "signed_plan_attachment_update", "signed_plan_content_update"):
            schema_editor.execute(f"DROP TRIGGER {name}")


class Migration(migrations.Migration):
    dependencies = [("casework", "0026_intervention_plans")]
    operations = [migrations.RunPython(install, uninstall)]
