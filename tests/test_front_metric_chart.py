"""metricChartSvg: серия из одной точки в sparse-режиме рисует график, не заглушку."""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

APP = (pathlib.Path(__file__).parent.parent / "src" / "tjapp" / "static"
       / "app.js").read_text(encoding="utf-8")

needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="нужен node")


def _chart(series, base=None, direction="high_bad", sparse=False):
    fn = re.search(r"function metricChartSvg[\s\S]*?\n\}", APP).group(0)
    js = (f'const T=k=>k;const fmt=x=>x==null?"—":(Math.round(x*10)/10);'
          f'{fn};console.log(metricChartSvg({json.dumps(series)},'
          f'{json.dumps(base)},{json.dumps(direction)},'
          f'{json.dumps(sparse)}))')
    return subprocess.run(["node", "-e", js], capture_output=True,
                          text=True, check=True).stdout


@needs_node
def test_single_point_sparse_draws_point_and_base():
    out = _chart([["2026-07-15", 2100]], base=2361, sparse=True)
    assert "<svg" in out
    assert "chart.no_data" not in out
    assert "2100" in out
    assert "07-15" in out
    assert "chart.bench" in out


@needs_node
def test_single_point_without_sparse_keeps_placeholder():
    out = _chart([["2026-07-15", 2100]], base=2361, sparse=False)
    assert "chart.no_data" in out


@needs_node
def test_empty_series_sparse_keeps_placeholder():
    out = _chart([], base=2361, sparse=True)
    assert "chart.no_data" in out


def test_nutr_week_chart_called_with_sparse():
    assert "metricChartSvg(m.series||[],m.base,m.dir,true)" in APP
