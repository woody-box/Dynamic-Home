import os
import json
import appdaemon.plugins.hass.hassapi as hass

class DynamicSuiteBackup(hass.Hass):
    """File-backed backup/restore for Dynamic Suite.

    Services (domain 'appdaemon'):
      - appdaemon/dynamic_suite_backup/save
      - appdaemon/dynamic_suite_backup/restore

    save:
      path: "dynamic_suite/dc/common/dc_common_backup.json"
      entities: ["input_boolean.x", ...] OR JSON string list
      payload: {...} OR JSON string dict (optional). If provided, used as-is.

    restore:
      path: "dynamic_suite/dc/common/dc_common_backup.json"
    """

    def initialize(self):
        self.register_service("dynamic_suite_backup/save", self.svc_save)
        self.register_service("dynamic_suite_backup/restore", self.svc_restore)
        self.log("DynamicSuiteBackup ready")

    BASE_DIR = "/config"

    def _full_path(self, rel_path: str):
        """Resolve rel_path under BASE_DIR, rejecting path traversal.

        Returns the absolute path if it stays inside BASE_DIR, else None.
        """
        rel_path = (rel_path or "").lstrip("/")
        base = os.path.realpath(self.BASE_DIR)
        full = os.path.realpath(os.path.join(base, rel_path))
        if full != base and not full.startswith(base + os.sep):
            return None
        return full

    def _json_load(self, v, default):
        if v is None:
            return default
        if isinstance(v, (dict, list)):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                return default
            return json.loads(v)
        return default

    def svc_save(self, namespace, domain, service, data):
        path = data.get("path")
        if not path:
            self.error("save: Missing data.path")
            return

        payload = data.get("payload")
        entities = data.get("entities")

        if payload is not None:
            d = self._json_load(payload, {})
            if not isinstance(d, dict):
                self.error("save: payload must be a dict")
                return
        else:
            ents = self._json_load(entities, [])
            if not isinstance(ents, list) or not ents:
                self.error("save: Missing data.entities (or empty)")
                return

            d = {}
            for eid in ents:
                st = self.get_state(eid)
                if st is None:
                    continue
                if str(st) in ["unknown", "unavailable", "none", ""]:
                    continue
                d[eid] = st

        full = self._full_path(path)
        if not full:
            self.error(f"save: Rejected unsafe path (outside {self.BASE_DIR}): {path}")
            return
        os.makedirs(os.path.dirname(full), exist_ok=True)

        tmp = full + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, full)

        self.log(f"Backup saved ({len(d)} items) -> {full}")

    def svc_restore(self, namespace, domain, service, data):
        path = data.get("path")
        if not path:
            self.error("restore: Missing data.path")
            return

        full = self._full_path(path)
        if not full:
            self.error(f"restore: Rejected unsafe path (outside {self.BASE_DIR}): {path}")
            return
        if not os.path.exists(full):
            msg = f"restore: File not found: {full}"
            self.error(msg)
            self.call_service("persistent_notification/create",
                              title="DynamicSuite backup restore",
                              message=msg)
            return

        with open(full, "r", encoding="utf-8") as f:
            d = json.load(f) or {}

        if not isinstance(d, dict):
            self.error("restore: Invalid file content (expected dict)")
            return

        for eid, val in d.items():
            dom = eid.split(".", 1)[0]
            try:
                if dom == "input_boolean":
                    self.call_service(f"input_boolean/turn_{'on' if str(val).lower()=='on' else 'off'}", entity_id=eid)
                elif dom == "input_number":
                    self.call_service("input_number/set_value", entity_id=eid, value=float(val))
                elif dom == "input_select":
                    self.call_service("input_select/select_option", entity_id=eid, option=str(val))
                elif dom == "input_text":
                    self.call_service("input_text/set_value", entity_id=eid, value=str(val)[:255])
                elif dom == "input_datetime":
                    self.call_service("input_datetime/set_datetime", entity_id=eid, datetime=str(val))
                else:
                    continue
            except Exception as ex:
                self.error(f"restore: Failed applying {eid}={val}: {ex}")

        self.log(f"Restore applied ({len(d)} items) <- {full}")
