"""Static-site generator for morning_brief (PR-2, plan v2 §C).

Public surface:
    - site_generator.generate_site(briefing, output_dir, ...)
    - search_index.build(archive_root)
    - renderer_adapter.build_template_context(briefing, ...)

The package is only activated when the CLI is invoked with
``--renderer=site`` (plan v2 §D8 PR-2). The default ``eml`` renderer
path (``morning_brief.renderer``) is untouched.
"""
