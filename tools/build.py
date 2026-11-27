#!/usr/bin/env python3
"""Build the release assets and the catalogs from the sources in this repository.

    python3 tools/build.py --assets-url URL --catalog-url URL [--specify PATH]

--assets-url   where this release's assets will be downloadable, e.g.
               https://github.com/kandy-babbel/whetstone/releases/download/v0.3.0
--catalog-url  where catalog/ will be readable, e.g.
               https://raw.githubusercontent.com/kandy-babbel/whetstone/main/catalog
--specify      the Spec Kit CLI, used to build the bundle zip (default: specify)

Writes (dist/ is emptied first):
  dist/<extension>-<version>.zip   one per extension, with LICENSE   (release assets)
  dist/<preset>-<version>.zip      one per preset, with LICENSE      (release assets)
  dist/<workflow>-<version>.yml    one per workflow                  (release assets)
  dist/<bundle>-<version>.zip      one per bundle directory          (release assets)
  catalog/extensions.json, catalog/presets.json, catalog/workflows.json, catalog/bundles.json   (commit)

Each catalog entry carries its sha256. When an entry's version changes, the version it
replaces moves into the entry's `releases`, so earlier releases stay installable.
The bundles are bundle/ (whetstone, the review) and each bundle-*/ beside it (bundle-plan/: whetstone-planner,
installed on its own). A bundle's id must not be a component's: their assets would share a name. Each extension, preset and workflow belongs to exactly one bundle, and every component and
bundle carries the same version.
catalog/steps.json is maintained by hand; its decision pin must match bundle.yml. Requires PyYAML.
"""
import argparse, datetime, hashlib, json, shutil, subprocess, sys, zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CAT = ROOT / "catalog"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def zip_dir(src: Path, dest: Path, extra: dict):
    """Reproducible zip: sorted paths, fixed timestamps, no caches; extra maps archive name -> file."""
    files = {p.relative_to(src).as_posix(): p for p in src.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.name != ".DS_Store"}
    files.update(extra)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            p = files[name]
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.external_attr = (0o755 if p.stat().st_mode & 0o111 else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())


def merge(old_entries: dict, entry: dict, url_key: str) -> dict:
    """Carry the previous catalog's history forward; a replaced current version becomes a release."""
    old = old_entries.get(entry["id"])
    releases = dict(old.get("releases", {})) if old else {}
    if old and old.get("version") != entry["version"]:
        if not old.get("sha256"):
            sys.exit(f"{entry['id']} {old['version']} in the old catalog has no sha256; it cannot be kept as a release")
        releases[old["version"]] = {k: old[k] for k in (url_key, "sha256", "requires") if k in old}
    releases.pop(entry["version"], None)
    return {**entry, "releases": releases} if releases else entry


def load(name: str, key: str) -> dict:
    p = CAT / name
    return json.loads(p.read_text())[key] if p.exists() else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-url", required=True)
    ap.add_argument("--catalog-url", required=True)
    ap.add_argument("--specify", default="specify")
    a = ap.parse_args()
    assets, cat = a.assets_url.rstrip("/"), a.catalog_url.rstrip("/")

    bundle_dirs = [ROOT / "bundle"] + sorted(d for d in ROOT.glob("bundle-*") if (d / "bundle.yml").is_file())
    bundles = [(d, yaml.safe_load((d / "bundle.yml").read_text())) for d in bundle_dirs]
    version = str(bundles[0][1]["bundle"]["version"])
    errors = [f"bundle {doc['bundle']['id']} {doc['bundle']['version']}: bundle is {version}"
              for _, doc in bundles if str(doc["bundle"]["version"]) != version]
    pinned, owner = {}, {}
    for _, doc in bundles:
        for k in ("extensions", "presets", "workflows", "steps"):
            for c in doc["provides"].get(k, []):
                key = (k, c["id"])
                if key in owner and k != "steps":
                    errors.append(f"{k[:-1]} {c['id']} is in both {owner[key]['id']} and {doc['bundle']['id']}")
                pinned[key], owner[key] = str(c["version"]), doc["bundle"]
    steps = load("steps.json", "steps")
    for (kind, cid), v in pinned.items():
        if kind == "steps" and steps.get(cid, {}).get("version") != v:
            errors.append(f"bundle pins step {cid} {v}, catalog/steps.json has {steps.get(cid, {}).get('version')}")

    dist = ROOT / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    dist.mkdir()
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    license_file = ROOT / "LICENSE"

    old_ext = load("extensions.json", "extensions")
    ext_cat = {"schema_version": "1.0", "updated_at": now, "catalog_url": f"{cat}/extensions.json", "extensions": {}}
    for d in sorted((ROOT / "extensions").iterdir()):
        doc = yaml.safe_load((d / "extension.yml").read_text())
        m = doc["extension"]
        if str(m["version"]) != version or pinned.get(("extensions", m["id"])) != version:
            errors.append(f"extension {m['id']} {m['version']}: bundle is {version}")
        name = f"{m['id']}-{m['version']}.zip"
        zip_dir(d, dist / name, {"LICENSE": license_file})
        ext_cat["extensions"][m["id"]] = merge(old_ext, {
            "id": m["id"], "name": m["name"], "description": " ".join(str(m["description"]).split()),
            "author": m.get("author", ""), "version": str(m["version"]), "download_url": f"{assets}/{name}",
            "sha256": sha256(dist / name), "license": m.get("license", ""), "requires": doc.get("requires", {}),
            "tags": ["whetstone"]}, "download_url")

    old_pre = load("presets.json", "presets")
    pre_cat = {"schema_version": "1.0", "updated_at": now, "catalog_url": f"{cat}/presets.json", "presets": {}}
    for d in sorted((ROOT / "presets").iterdir()):
        doc = yaml.safe_load((d / "preset.yml").read_text())
        m = doc["preset"]
        if str(m["version"]) != version or pinned.get(("presets", m["id"])) != version:
            errors.append(f"preset {m['id']} {m['version']}: bundle is {version}")
        name = f"{m['id']}-{m['version']}.zip"
        zip_dir(d, dist / name, {"LICENSE": license_file})
        provided = doc.get("provides", {}).get("templates", [])
        pre_cat["presets"][m["id"]] = merge(old_pre, {
            "id": m["id"], "name": m["name"], "description": " ".join(str(m["description"]).split()),
            "author": m.get("author", ""), "repository": m.get("repository", ""), "version": str(m["version"]),
            "download_url": f"{assets}/{name}", "sha256": sha256(dist / name), "license": m.get("license", ""),
            "requires": doc.get("requires", {}),
            "provides": {k: sum(1 for t in provided if t.get("type") == k[:-1]) for k in ("templates", "commands")},
            "tags": ["whetstone"]}, "download_url")

    old_wf = load("workflows.json", "workflows")
    wf_cat = {"schema_version": "1.0", "updated_at": now, "workflows": {}}
    for p in sorted((ROOT / "workflows").glob("*.yml")):
        doc = yaml.safe_load(p.read_text())
        w = doc["workflow"]
        if str(w["version"]) != version or pinned.get(("workflows", w["id"])) != version:
            errors.append(f"workflow {w['id']} {w['version']}: bundle is {version}")
        name = f"{w['id']}-{w['version']}.yml"
        shutil.copyfile(p, dist / name)
        wf_cat["workflows"][w["id"]] = merge(old_wf, {
            "id": w["id"], "name": w["name"], "description": w["description"], "author": w.get("author", ""),
            "version": str(w["version"]), "url": f"{assets}/{name}", "sha256": sha256(dist / name),
            "requires": doc.get("requires", {}),
            "license": owner.get(("workflows", w["id"]), {}).get("license", "")}, "url")

    built = {"extensions": ext_cat["extensions"], "presets": pre_cat["presets"], "workflows": wf_cat["workflows"]}
    missing = {k for k in pinned if k[0] != "steps" and k[1] not in built[k[0]]}
    errors += [f"bundle names {k[0][:-1]} {k[1]}, which has no source" for k in sorted(missing)]
    if errors:
        sys.exit("cannot build:\n  " + "\n  ".join(errors))

    old_b = load("bundles.json", "bundles")
    b_cat = {"schema_version": "1.0", "updated_at": now, "bundles": {}}
    for d, bundle in bundles:
        b = bundle["bundle"]
        bundle_zip = dist / f"{b['id']}-{version}.zip"
        if bundle_zip.exists():
            sys.exit(f"bundle {b['id']} would overwrite {bundle_zip.name}, another component's asset: rename the bundle")
        r = subprocess.run([a.specify, "bundle", "build", "--path", str(d), "--output", str(dist)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not bundle_zip.exists():
            sys.exit(f"specify bundle build failed for {d.name}:\n{r.stdout}{r.stderr}")
        counts = {k: len(bundle["provides"].get(k, [])) for k in ("extensions", "presets", "steps", "workflows")}
        b_cat["bundles"][b["id"]] = merge(old_b, {
            "id": b["id"], "name": b["name"], "version": version, "role": b.get("role", "developer"),
            "description": b["description"], "author": b.get("author", ""), "license": b.get("license", ""),
            "download_url": f"{assets}/{bundle_zip.name}", "sha256": sha256(bundle_zip),
            "requires": {"speckit_version": bundle["requires"]["speckit_version"]}, "provides": counts,
            "tags": bundle.get("tags", []), "verified": False}, "download_url")

    (CAT / "extensions.json").write_text(json.dumps(ext_cat, indent=1) + "\n")
    (CAT / "presets.json").write_text(json.dumps(pre_cat, indent=1) + "\n")
    (CAT / "workflows.json").write_text(json.dumps(wf_cat, indent=1) + "\n")
    (CAT / "bundles.json").write_text(json.dumps(b_cat, indent=1) + "\n")
    print(f"built {version}: {len(ext_cat['extensions'])} extensions, {len(pre_cat['presets'])} presets, "
          f"{len(wf_cat['workflows'])} workflows, "
          f"bundles {', '.join(sorted(b_cat['bundles']))} -> dist/; catalogs -> catalog/")


if __name__ == "__main__":
    main()
