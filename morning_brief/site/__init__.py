"""Static-site generator for morning_brief (PR-2, plan v2 §C).

Public surface:
    - site_generator.generate_site(briefing, output_dir, ...)
    - search_index.build(archive_root)
    - renderer_adapter.build_template_context(briefing, ...)

As of PR-4, this is the sole renderer — the CLI always writes to the static
site, and the legacy ``morning_brief.renderer`` EML path has been removed.
"""
