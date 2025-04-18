Type: Refactor

Issues:
1. **Data Structure Refactor Impact**
   - There is a significant refactoring of the "ACL" data representation throughout the app, replacing list-based form data with dict-based (JSON) structured fields. There is now a split into multiple fields in the `ACL` model (e.g., `create_info`, `traffic_rules`, etc.), replacing previous reliance on the single `acltext` field.
   - **Migration Flag**: The `acltext` field will remain until at least 01.06.2025, and a migration flag `is_migrated` is introduced for smooth transition. But there's a risk of data inconsistency if the migration or usage is not handled exhaustively.

2. **Potential Data Migration Incompleteness & Data Loss**
   - The migration script in `accesslist/management/commands/split_acl_data.py` depends on particular keys existing in `acltext`. If they are missing or if the format varies, information may be lost or skipped (e.g., no fallback/merge logic, only `if acl.acltext == []: continue` skips empty values but not malformed/partial ones).
   - The management commands updating records silently print errors but do not log or report them reliably.

3. **Error Handling**
   - Many management commands catch broad exceptions and merely print them or output to `stdout`; this can lead to silent migration failures. This is especially problematic during one-off migrations.

4. **Backward Compatibility Risks**
   - Some code (e.g., in `views.py`, template logic) seems to expect the new dict-based format for session and DB data. If some objects are not yet migrated, old logic may break (e.g., attempts to access keys like `full_name` not present in pre-migrated data). Some defensive checks are included but may not be thorough.

5. **Template & Form Changes**
   - Extensive changes from list to dict and from positional to named form fields across all templates and JS. If any overlooked place still expects the old format, subtle bugs may appear.
   - AJAX, JavaScript, and client-side code may make assumptions that would not hold for legacy/pre-migrated data.
   - The main.js code for adding/removing rows relies on naming conventions and regexes, which could break if form elements change structure or naming.

6. **Search Functionality**
   - The `DeepSearch` function now queries over the new split fields but only for migrated data. Objects still using only `acltext` may not be found.

7. **Security/Validation**
   - There is little to no added input validation when transforming between data structures or receiving external POST data, which can lead to injection or logical bugs if untrusted input arrives.

8. **Missing Tests**
   - For a change of this scale and risk, there is no evidence of added or updated automated tests.

Needs more context?
Yes. Additional context needed:
- The current and historical usage of the `acltext` field and whether any legacy dependencies (other modules, cron jobs, reporting) may remain.
- Existing automated tests and migration test plan.
- Validation/cleaning rules for each new field (`create_info`, `traffic_rules`, etc.), especially for downstream consumers of this structured data.
- Admin/backoffice workflows for handling failed or partial migrations.
- Clarity over error logging/reporting policy during migration and on production.

**Recommendation:** This refactor is potentially dangerous without exhaustive testing and a clear plan for rollback, error reporting, and legacy compatibility handling. All critical code paths (including external integrations) should be re-verified for compatibility with both pre- and post-migration data, and field-level validation and error reporting should be strengthened.