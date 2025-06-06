# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2017-2018 CERN.
# Copyright (C) 2022-2024 Graz University of Technology.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration."""

import sys
import types
from collections import namedtuple
from copy import deepcopy

import pytest
from flask import Flask, g
from flask_limiter import Limiter

from invenio_app.config import APP_DEFAULT_SECURE_HEADERS, set_rate_limit
from invenio_app.ext import useragent_and_ip_limit_key
from invenio_app.helpers import obj_or_import_string


@pytest.fixture()
def base_app():
    """Flask application fixture."""
    app_ = Flask("testapp")
    app_.config.update(
        SECRET_KEY="SECRET_KEY",
        TESTING=True,
    )

    app_.config["APP_DEFAULT_SECURE_HEADERS"] = deepcopy(APP_DEFAULT_SECURE_HEADERS)
    app_.config["APP_DEFAULT_SECURE_HEADERS"]["force_https"] = False

    @app_.route("/requestid")
    def requestid():
        from flask import g  # Prevent pytest problems

        return g.request_id if g and hasattr(g, "request_id") else ""

    @app_.route("/limited_rate")
    def limited_rate():
        return "test"

    @app_.route("/unlimited_rate")
    def unlimited_rate():
        return "test"

    return app_


@pytest.fixture()
def app_with_no_limiter(base_app):
    """Flask application fixture without limiter registered."""
    with base_app.app_context():
        yield base_app


@pytest.fixture()
def app(base_app):
    """Flask application fixture."""
    base_app.config.update(
        TRUSTED_HOSTS=["localhost"],
        RATELIMIT_APPLICATION=set_rate_limit,
        RATELIMIT_GUEST_USER="2 per second",
        RATELIMIT_AUTHENTICATED_USER="5 per second",
        RATELIMIT_PER_ENDPOINT={"unlimited_rate": "200 per second"},
        RATELIMIT_HEADERS_ENABLED=True,
    )
    Limiter(
        base_app,
        key_func=obj_or_import_string(
            base_app.config.get("RATELIMIT_KEY_FUNC"),
            default=useragent_and_ip_limit_key,
        ),
    )
    with base_app.app_context():
        yield base_app


@pytest.fixture()
def wsgi_apps():
    """Wsgi app fixture."""
    from invenio_base.app import create_app_factory
    from invenio_base.wsgi import create_wsgi_factory, wsgi_proxyfix

    def _config(app, **kwargs):
        app.config.update(
            SECRET_KEY="SECRET_KEY",
            TESTING=True,
        )
        app.config["APP_DEFAULT_SECURE_HEADERS"] = deepcopy(APP_DEFAULT_SECURE_HEADERS)
        app.config["APP_DEFAULT_SECURE_HEADERS"]["force_https"] = False

    # API
    create_api = create_app_factory(
        "invenio",
        config_loader=_config,
        wsgi_factory=wsgi_proxyfix(),
    )
    # UI
    create_ui = create_app_factory(
        "invenio",
        config_loader=_config,
        wsgi_factory=wsgi_proxyfix(),
    )
    # Combined
    create_app = create_app_factory(
        "invenio",
        config_loader=_config,
        wsgi_factory=wsgi_proxyfix(create_wsgi_factory({"/api": create_api})),
    )
    return create_app, create_ui, create_api


@pytest.fixture()
def push_rate_limit_to_context():
    """Push a custom rate limit to the Flask global context."""
    custom_rate_limit = "10 per second"
    setattr(g, "user_rate_limit", custom_rate_limit)
    return custom_rate_limit
