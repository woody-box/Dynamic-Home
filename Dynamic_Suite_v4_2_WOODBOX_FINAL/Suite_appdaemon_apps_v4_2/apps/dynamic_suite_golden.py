import os
import json
import appdaemon.plugins.hass.hassapi as hass

class DynamicSuiteGolden(hass.Hass):
    """File-backed golden record/verify for Dynamic Suite.

    Services (domain 'appdaemon'):
      - appdaemon/dynamic_suite_golden/record
      - appdaemon/dynamic_suite_golden/verify

    data:
      path: "dynamic_suite/dc/zone01/dc_zone01_golden.json"
      case: "ola_frio_extremo"
      entity_ids: ["sensor.xxx", ...] OR JSON string list
      tolerances: {"sensor.xxx": 0.05, ...} OR JSON string dict (optional)
    """

    def initialize(self):
        self.register_service("dynamic_suite_golden/record", self.svc_record)
        self.register_service("dynamic_suite_golden/verify", self.svc_verify)
        self.log("DynamicSuiteGolden ready")

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

    def _to_float(self, v):
        try:
            return float(str(v))
        except Exception:
            return None

    def _snapshot(self, entity_ids):
        out = {}
        for eid in entity_ids:
            st = self.get_state(eid)
            out[eid] = st if st is not None else None
        return out

    def svc_record(self, namespace, domain, service, data):
        path = data.get("path")
        case = data.get("case")
        if not path or not case:
            self.error("record: Missing path/case")
            return

        entity_ids = self._json_load(data.get("entity_ids"), [])
        if not isinstance(entity_ids, list) or not entity_ids:
            self.error("record: Missing entity_ids")
            return

        full = self._full_path(path)
        if not full:
            self.error(f"record: Rejected unsafe path (outside {self.BASE_DIR}): {path}")
            return
        os.makedirs(os.path.dirname(full), exist_ok=True)

        db = {}
        if os.path.exists(full):
            with open(full, "r", encoding="utf-8") as f:
                db = json.load(f) or {}

        db[str(case)] = {
            "ts": self.datetime().isoformat(timespec="seconds"),
            "outputs": self._snapshot(entity_ids),
        }

        tmp = full + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        os.replace(tmp, full)

        self.log(f"GOLDEN recorded case={case} -> {full}")

    def svc_verify(self, namespace, domain, service, data):
        path = data.get("path")
        case = data.get("case")
        if not path or not case:
            self.error("verify: Missing path/case")
            return

        entity_ids = self._json_load(data.get("entity_ids"), [])
        if not isinstance(entity_ids, list) or not entity_ids:
            self.error("verify: Missing entity_ids")
            return

        tolerances = self._json_load(data.get("tolerances"), {}) or {}

        full = self._full_path(path)
        if not full:
            self.error(f"verify: Rejected unsafe path (outside {self.BASE_DIR}): {path}")
            return
        if not os.path.exists(full):
            msg = f"Golden file not found: {full}. Run record first."
            self.error(msg)
            self.call_service("persistent_notification/create",
                              title="DynamicSuite golden",
                              message=msg)
            return

        with open(full, "r", encoding="utf-8") as f:
            db = json.load(f) or {}

        if str(case) not in db:
            msg = f"Case '{case}' not found in {full}. Run record for this case first."
            self.error(msg)
            self.call_service("persistent_notification.create",
                              title="DynamicSuite golden",
                              message=msg)
            return

        expected = db[str(case)].get("outputs", {})
        current = self._snapshot(entity_ids)

        mismatches = []
        for eid in entity_ids:
            exp = expected.get(eid)
            cur = current.get(eid)
            tol = tolerances.get(eid)

            if tol is not None:
                exp_f = self._to_float(exp)
                cur_f = self._to_float(cur)
                tol_f = self._to_float(tol)
                if exp_f is None or cur_f is None or tol_f is None or abs(exp_f - cur_f) > tol_f:
                    mismatches.append(f"{eid}: exp={exp} cur={cur} tol={tol}")
            else:
                if str(exp) != str(cur):
                    mismatches.append(f"{eid}: exp='{exp}' cur='{cur}'")

        if mismatches:
            msg = f"GOLDEN FAIL case={case}\n- " + "\n- ".join(mismatches)
            self.error(msg)
            self.call_service("persistent_notification/create",
                              title="DynamicSuite golden FAIL",
                              message=msg)
        else:
            self.log(f"GOLDEN PASS case={case}")
