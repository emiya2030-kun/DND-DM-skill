# Generalize Class Feature Runtime Helpers

## Context
Current shared runtime helpers only support the `fighter` bucket, which forces callers to depend on that specific class when reading or writing runtime state. The martial class feature templates work underway expect a more flexible API so other class buckets (monk, rogue, etc.) can reuse the same helpers. At the same time, option normalization logic lives outside this directory and lacks encapsulation.

## Goals
1. Provide reusable helpers to read and ensure per-class runtime buckets while retaining compatibility with existing fighter helpers.
2. Allow runtime helpers to accept either a runtime dictionary or an entity object and normalize missing buckets into empty dicts.
3. Introduce a lightweight normalization helper for class feature option maps that only standardizes the top-level keys (strip + lowercase) and leaves nested structures untouched.
4. Back both features with unit tests that explicitly demonstrate the desired behavior.

## Approach

### Runtime helpers
- Add `get_class_runtime(entity_or_class_features, class_id)` and `ensure_class_runtime(entity_or_class_features, class_id)` that reuse `_read_class_features`/`_ensure_class_features` to locate or create the requested bucket. Return an empty dict if the bucket is missing or not a dict so callers can safely assign fields without additional guards.
- Keep `get_fighter_runtime` and `ensure_fighter_runtime` as thin wrappers around the new generic helpers so existing consumers continue to work without changes.
- Document the helpers in `__init__.py` exports alongside the fighter helpers to make the new API discoverable.

### Option normalization
- Add `normalize_class_feature_options(raw)` that accepts any input, returns an empty dict for non-dicts, and otherwise strips/lowers each str key while leaving values entirely untouched (even nested dicts or lists). This keeps the helper simple and focused on top-level flag normalization.

### Testing
- Extend `test_class_feature_runtime_helpers.py` with specific cases for generic runtime helpers (e.g., `monk` focus points) and normalization behavior (preserving nested dictionaries while normalizing keys). The new tests should start failing because the helpers do not yet exist.
- Keep the existing fighter-specific tests intact so we do not regress other behaviors.

## Risks & Open Questions
- Normalizing only top-level keys means callers must handle nested structure validation separately. If deeper normalization becomes necessary later, we can layer additional helpers that traverse nested dicts.
- These helpers only touch class feature runtime structures; attack flow, encounter projection, or other runtime data remain untouched.
