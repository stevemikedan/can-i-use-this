"""
The pipeline as plain Python — classify → identify → decompose → research →
rules → compare → assemble — that agent/ (google-adk) wraps later.

    from pipeline.music import run_music
    response = run_music(AssetQuery(raw_input="West End Blues — Louis Armstrong",
                                    intent=Intent.FILM_TV))

    python -m pipeline "West End Blues" "Louis Armstrong" --intent film_tv
"""
