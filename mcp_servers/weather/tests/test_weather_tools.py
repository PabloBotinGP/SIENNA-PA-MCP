import pytest

import asyncio

import weather


@pytest.mark.asyncio
async def test_get_alerts_success(monkeypatch):
    async def fake_make_nws_request(url: str):
        return {
            "features": [
                {"properties": {"event": "Test Event", "areaDesc": "Test Area", "severity": "Minor", "description": "Desc", "instruction": "Instr"}}
            ]
        }

    monkeypatch.setattr(weather, "make_nws_request", fake_make_nws_request)
    res = await weather.get_alerts("CO")
    assert "Test Event" in res


@pytest.mark.asyncio
async def test_get_alerts_failure(monkeypatch):
    async def fake_none(url: str):
        return None

    monkeypatch.setattr(weather, "make_nws_request", fake_none)
    res = await weather.get_alerts("CO")
    assert "Unable to fetch" in res


@pytest.mark.asyncio
async def test_get_forecast_success(monkeypatch):
    async def fake_make_nws_request(url: str):
        if "/points/" in url:
            return {"properties": {"forecast": "https://api.weather.gov/fake/forecast"}}
        else:
            return {"properties": {"periods": [{"name": "Saturday", "temperature": 20, "temperatureUnit": "F", "windSpeed": "10 mph", "windDirection": "NW", "detailedForecast": "Sunny."}]}}

    monkeypatch.setattr(weather, "make_nws_request", fake_make_nws_request)
    res = await weather.get_forecast(40.0, -105.0, periods_count=1)
    assert "Saturday" in res


@pytest.mark.asyncio
async def test_get_forecast_failure(monkeypatch):
    async def fake_none(url: str):
        return None

    monkeypatch.setattr(weather, "make_nws_request", fake_none)
    res = await weather.get_forecast(40.0, -105.0)
    assert "Unable to fetch" in res
