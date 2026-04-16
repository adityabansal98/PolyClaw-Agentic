"""Portfolio, positions, balance, trade history — agent-scoped reads."""

from flask import g, jsonify

from polyclaw.web.api_v1 import api_v1, require_auth


def _svc():
    from polyclaw.web.app import get_trading_service

    return get_trading_service()


@api_v1.route("/portfolio")
def get_portfolio():
    err = require_auth()
    if err:
        return err
    p = _svc().get_portfolio(g.agent_id)
    return jsonify(p.model_dump())


@api_v1.route("/positions")
def get_positions():
    err = require_auth()
    if err:
        return err
    positions = _svc().get_positions(g.agent_id)
    return jsonify([p.model_dump() for p in positions])


@api_v1.route("/balance")
def get_balance():
    err = require_auth()
    if err:
        return err
    return jsonify({"cash_balance": _svc().get_balance(g.agent_id)})


@api_v1.route("/trades")
def get_trade_history():
    err = require_auth()
    if err:
        return err
    return jsonify({"items": _svc().get_trade_history(g.agent_id)})
