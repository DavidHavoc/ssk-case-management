from django.db import migrations


POSTGRES = """
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE casework_beneficiarystaffingperiod ADD CONSTRAINT staffing_no_overlap
EXCLUDE USING gist (beneficiary_id WITH =, daterange(valid_from, valid_to, '[)') WITH &&);
CREATE FUNCTION ssk_staffing_history_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Staffing history is preserved';
    END IF;
    PERFORM 1 FROM casework_beneficiary WHERE id=NEW.beneficiary_id FOR UPDATE;
    IF TG_OP = 'UPDATE' THEN
        IF (NEW.beneficiary_id, NEW.lead_id, NEW.helper_id, NEW.valid_from,
            NEW.confirmed_by_id, NEW.migration_backfill)
            IS DISTINCT FROM (OLD.beneficiary_id, OLD.lead_id, OLD.helper_id, OLD.valid_from,
            OLD.confirmed_by_id, OLD.migration_backfill)
            OR (NEW.valid_to IS DISTINCT FROM OLD.valid_to AND
                (NEW.valid_to IS NULL OR NEW.valid_to < CURRENT_DATE
                 OR (OLD.valid_to IS NOT NULL AND NEW.valid_to > OLD.valid_to))) THEN
            RAISE EXCEPTION 'Staffing history is immutable except prospective closure';
        END IF;
    ELSE
        IF NEW.valid_from < CURRENT_DATE OR NEW.migration_backfill OR NEW.confirmed_by_id IS NULL THEN
            RAISE EXCEPTION 'New staffing requires prospective manager confirmation';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM accounts_user u
            WHERE u.id = NEW.confirmed_by_id AND u.is_active
            AND (u.is_superuser OR EXISTS (
                SELECT 1 FROM accounts_user_groups ug JOIN auth_group g ON g.id=ug.group_id
                WHERE ug.user_id=u.id AND g.name IN ('System Manager', 'SSK Center Coordinator')
            ))
        ) THEN RAISE EXCEPTION 'Only a manager or coordinator may confirm staffing'; END IF;
        IF NOT EXISTS (
            SELECT 1 FROM casework_serviceenrollment e
            JOIN casework_enrollmentcenterplacement p ON p.enrollment_id=e.id
            JOIN centers_center c ON c.id=p.center_id
            WHERE e.beneficiary_id=NEW.beneficiary_id AND c.is_active
            AND (e.status NOT IN ('exited','completed','cancelled') OR e.end_date>NEW.valid_from)
            AND p.valid_from <= NEW.valid_from AND (p.valid_to IS NULL OR p.valid_to > NEW.valid_from)
            AND EXISTS (
                SELECT 1 FROM centers_specialistprofile sp JOIN centers_staffprofile s ON s.id=sp.staff_profile_id
                JOIN accounts_user u ON u.id=s.user_id
                JOIN centers_specialistcenterassignment a ON a.specialist_id=sp.id
                WHERE sp.id=NEW.lead_id AND s.status='active' AND u.is_active AND a.center_id=p.center_id
            )
            AND (NEW.helper_id IS NULL OR EXISTS (
                SELECT 1 FROM centers_specialistprofile sp JOIN centers_staffprofile s ON s.id=sp.staff_profile_id
                JOIN accounts_user u ON u.id=s.user_id
                JOIN centers_specialistcenterassignment a ON a.specialist_id=sp.id
                WHERE sp.id=NEW.helper_id AND s.status='active' AND u.is_active AND a.center_id=p.center_id
            ))
            AND EXISTS (
                SELECT 1 FROM accounts_user u WHERE u.id=NEW.confirmed_by_id AND
                (u.is_superuser OR EXISTS (
                    SELECT 1 FROM accounts_user_groups ug JOIN auth_group g ON g.id=ug.group_id
                    WHERE ug.user_id=u.id AND g.name='System Manager'
                ) OR EXISTS (
                    SELECT 1 FROM centers_staffprofile s JOIN centers_staffprofile_centers sc ON sc.staffprofile_id=s.id
                    WHERE s.user_id=u.id AND s.status='active' AND sc.center_id=p.center_id
                ))
            )
        ) THEN RAISE EXCEPTION 'Staffing requires active eligible specialists and an authorized ongoing placement'; END IF;
    END IF;
    IF TG_OP='UPDATE' THEN NEW.updated_at=clock_timestamp(); END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER staffing_history_guard BEFORE INSERT OR UPDATE OR DELETE
ON casework_beneficiarystaffingperiod FOR EACH ROW EXECUTE FUNCTION ssk_staffing_history_guard();
CREATE FUNCTION ssk_legacy_grant_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Legacy staffing access is a frozen migration snapshot'; END $$;
CREATE TRIGGER legacy_grant_guard BEFORE INSERT OR UPDATE ON casework_legacystaffinggrant
FOR EACH ROW EXECUTE FUNCTION ssk_legacy_grant_guard();
"""


SAME_DAY_AUTHORS = """
    EXISTS (SELECT 1 FROM casework_servicevisit v WHERE v.beneficiary_id=NEW.beneficiary_id
        AND v.visit_date=NEW.valid_from AND v.specialist_id<>NEW.lead_id
        AND (NEW.helper_id IS NULL OR v.specialist_id<>NEW.helper_id))
    OR EXISTS (SELECT 1 FROM casework_assessment a WHERE a.beneficiary_id=NEW.beneficiary_id
        AND a.assessment_date=NEW.valid_from AND a.specialist_id<>NEW.lead_id
        AND (NEW.helper_id IS NULL OR a.specialist_id<>NEW.helper_id))
    OR EXISTS (SELECT 1 FROM casework_individualplan p WHERE p.beneficiary_id=NEW.beneficiary_id
        AND p.plan_start_date=NEW.valid_from AND p.specialist_id<>NEW.lead_id
        AND (NEW.helper_id IS NULL OR p.specialist_id<>NEW.helper_id))
    OR EXISTS (SELECT 1 FROM casework_assessmentresponsiblespecialist r
        JOIN casework_assessment a ON a.id=r.assessment_id
        WHERE a.beneficiary_id=NEW.beneficiary_id AND a.assessment_date=NEW.valid_from
        AND r.specialist_id<>NEW.lead_id AND (NEW.helper_id IS NULL OR r.specialist_id<>NEW.helper_id))
"""
SAME_DAY_CLOSURE = """
    EXISTS (SELECT 1 FROM casework_servicevisit v WHERE v.beneficiary_id=NEW.beneficiary_id AND v.visit_date=NEW.valid_to)
    OR EXISTS (SELECT 1 FROM casework_assessment a WHERE a.beneficiary_id=NEW.beneficiary_id AND a.assessment_date=NEW.valid_to)
    OR EXISTS (SELECT 1 FROM casework_individualplan p WHERE p.beneficiary_id=NEW.beneficiary_id AND p.plan_start_date=NEW.valid_to)
"""


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        from django.conf import settings

        sql = POSTGRES.replace("    RETURN NEW;", f"""
            IF TG_OP='INSERT' AND NEW.valid_from=CURRENT_DATE AND ({SAME_DAY_AUTHORS}) THEN
                RAISE EXCEPTION 'Recorded casework already uses this date';
            END IF;
            IF TG_OP='UPDATE' AND NEW.valid_to IS DISTINCT FROM OLD.valid_to
                AND NEW.valid_to=CURRENT_DATE AND ({SAME_DAY_CLOSURE}) THEN
                RAISE EXCEPTION 'Recorded casework already uses this date';
            END IF;
            RETURN NEW;
        """)
        zone = settings.TIME_ZONE.replace("'", "''")
        schema_editor.execute(sql.replace("CURRENT_DATE", f"(CURRENT_TIMESTAMP AT TIME ZONE '{zone}')::date"))
    elif schema_editor.connection.vendor == "sqlite":
        # SQLite is a developer backend; PostgreSQL also protects concurrent raw writers.
        # Reuse the same SQL eligibility predicates on both supported backends.
        manager_start = POSTGRES.index("IF NOT EXISTS (") + len("IF ")
        manager_end = POSTGRES.index(" THEN RAISE EXCEPTION", manager_start)
        eligibility_start = POSTGRES.index("IF NOT EXISTS (", manager_end) + len("IF ")
        eligibility_end = POSTGRES.index(" THEN RAISE EXCEPTION", eligibility_start)
        manager = POSTGRES[manager_start:manager_end]
        eligibility = POSTGRES[eligibility_start:eligibility_end]
        schema_editor.execute(f"""
            CREATE TRIGGER staffing_appointment_insert BEFORE INSERT ON casework_beneficiarystaffingperiod BEGIN
                SELECT RAISE(ABORT, 'Recorded casework already uses this date') WHERE NEW.valid_from=CURRENT_DATE AND ({SAME_DAY_AUTHORS});
                SELECT RAISE(ABORT, 'New staffing requires prospective manager confirmation')
                WHERE NEW.valid_from < CURRENT_DATE OR NEW.migration_backfill OR NEW.confirmed_by_id IS NULL;
                SELECT RAISE(ABORT, 'Only a manager or coordinator may confirm staffing') WHERE {manager};
                SELECT RAISE(ABORT, 'Staffing requires eligible specialists and authorized placement') WHERE {eligibility};
            END;
        """)
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(f"""
            CREATE TRIGGER staffing_no_overlap_{operation.lower()} BEFORE {operation}
            ON casework_beneficiarystaffingperiod BEGIN
                SELECT RAISE(ABORT, 'Staffing periods cannot overlap') WHERE EXISTS (
                    SELECT 1 FROM casework_beneficiarystaffingperiod p
                    WHERE p.beneficiary_id=NEW.beneficiary_id AND p.id != NEW.id
                    AND (p.valid_to IS NULL OR p.valid_to > NEW.valid_from)
                    AND (NEW.valid_to IS NULL OR p.valid_from < NEW.valid_to)
                );
            END;
            """)
        schema_editor.execute(f"""
            CREATE TRIGGER staffing_history_update BEFORE UPDATE ON casework_beneficiarystaffingperiod BEGIN
                SELECT RAISE(ABORT, 'Recorded casework already uses this date') WHERE NEW.valid_to IS NOT OLD.valid_to AND NEW.valid_to=CURRENT_DATE AND ({SAME_DAY_CLOSURE});
                SELECT RAISE(ABORT, 'Staffing updates require a change timestamp') WHERE NEW.valid_to IS NOT OLD.valid_to AND NEW.updated_at=OLD.created_at;
                SELECT RAISE(ABORT, 'Staffing history is preserved') WHERE
                NEW.beneficiary_id IS NOT OLD.beneficiary_id OR NEW.lead_id IS NOT OLD.lead_id
                OR NEW.helper_id IS NOT OLD.helper_id OR NEW.valid_from IS NOT OLD.valid_from
                OR NEW.confirmed_by_id IS NOT OLD.confirmed_by_id OR NEW.migration_backfill IS NOT OLD.migration_backfill
                OR (NEW.valid_to IS NOT OLD.valid_to AND (NEW.valid_to IS NULL
                    OR NEW.valid_to < date('now') OR (OLD.valid_to IS NOT NULL AND NEW.valid_to > OLD.valid_to)));
            END;
        """)
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(f"""
            CREATE TRIGGER legacy_grant_{operation.lower()} BEFORE {operation} ON casework_legacystaffinggrant BEGIN
                SELECT RAISE(ABORT, 'Legacy staffing access is a frozen migration snapshot');
            END;
            """)


def uninstall(apps, schema_editor):
    from django.db.models import F, Q

    Period = apps.get_model("casework", "BeneficiaryStaffingPeriod")
    if Period.objects.using(schema_editor.connection.alias).filter(
        Q(migration_backfill=False) | ~Q(updated_at=F("created_at"))
    ).exists():
        raise RuntimeError("Staffing has changed since migration. Database guards remain installed; preserve the schema and review rollback.")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TRIGGER staffing_history_guard ON casework_beneficiarystaffingperiod")
        schema_editor.execute("DROP TRIGGER legacy_grant_guard ON casework_legacystaffinggrant")
        schema_editor.execute("DROP FUNCTION ssk_staffing_history_guard()")
        schema_editor.execute("DROP FUNCTION ssk_legacy_grant_guard()")
        schema_editor.execute("ALTER TABLE casework_beneficiarystaffingperiod DROP CONSTRAINT staffing_no_overlap")
    elif schema_editor.connection.vendor == "sqlite":
        for name in ("staffing_appointment_insert", "staffing_no_overlap_insert", "staffing_no_overlap_update", "staffing_history_update",
                     "legacy_grant_insert", "legacy_grant_update"):
            schema_editor.execute(f"DROP TRIGGER {name}")


class Migration(migrations.Migration):
    dependencies = [("casework", "0017_backfill_staffing_review")]
    operations = [migrations.RunPython(install, uninstall)]
