import importlib
mods = [
  "hushdesk.pdf.band_resolver",
  "hushdesk.pdf.spatial_index",
  "hushdesk.pdf.vitals_bounds",
  "hushdesk.pdf.mar_grid_extract",
  "hushdesk.pdf.rules_master",
  "hushdesk.pdf.rules_normalize",
]
for m in mods:
    importlib.import_module(m)
print("IMPORT_OK")
