import importlib
mods = [
  "hushdesk.pdf.band_resolver",
  "hushdesk.pdf.spatial_index",
  "hushdesk.pdf.vitals_bounds",
  "hushdesk.pdf.mar_grid_extract",
  "hushdesk.pdf.rules_master",
  "hushdesk.pdf.rules_normalize",
]
for mod in mods:
    importlib.import_module(mod)
print("IMPORT_OK")
