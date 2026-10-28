"""
pipeline/: turns the raw source files into a DuckDB warehouse.

    build.py     runs the SQL files in pipeline/sql/ in order (01, 02, 03 ...)
    quality.py   checks the finished warehouse and fails loudly on bad data
"""
