# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2017-2019 CERN.
# Copyright (C) 2022-2024 Graz University of Technology.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Invenio app extension."""

import warnings

from flask import Blueprint, g, request
from flask_limiter import Limiter
from flask_talisman import Talisman

from invenio_app.limiter import useragent_and_ip_limit_key

from . import config
from .helpers import ThemeJinjaLoader, obj_or_import_string, safe_redirect


class InvenioApp(object):
    """Invenio app extensions."""

    def __init__(self, app=None, **kwargs):
        r"""Extension initialization.

        :param app: An instance of :class:`~flask.Flask`.
        :param \**kwargs: Keyword arguments are passed to ``init_app`` method.
        """
        self.limiter = None
        self.talisman = None

        if app:
            self.init_app(app, **kwargs)

    def init_app(self, app, **kwargs):
        """Initialize application object.

        :param app: An instance of :class:`~flask.Flask`.
        """
        # Init the configuration
        self.init_config(app)

        # Enable secure HTTP headers
        if app.config["APP_ENABLE_SECURE_HEADERS"]:
            self.talisman = Talisman(
                app, **app.config.get("APP_DEFAULT_SECURE_HEADERS", {})
            )

        app.jinja_env.filters["safe_redirect"] = safe_redirect

        # Enable Rate limiter
        # Flask limiter needs to be initialised after talisman, since if the
        # talisman preprocessor doesn't run you will get an error on it's
        # afterprocessor.
        self.limiter = Limiter(
            app,
            key_func=obj_or_import_string(
                app.config.get("RATELIMIT_KEY_FUNC"), default=useragent_and_ip_limit_key
            ),
        )

        # Enable PING view
        if app.config["APP_HEALTH_BLUEPRINT_ENABLED"]:
            blueprint = Blueprint("invenio_app_ping", __name__)
            limiter = self.limiter

            @blueprint.route("/ping", methods=["HEAD", "OPTIONS", "GET"])
            @limiter.exempt
            def ping():
                """Load balancer ping view."""
                return "OK"

            ping.talisman_view_options = {"force_https": False}

            app.register_blueprint(blueprint)

        requestid_header = app.config.get("APP_REQUESTID_HEADER")
        if requestid_header:

            @app.before_request
            def set_request_id():
                """Extracts a request id from an HTTP header."""
                request_id = request.headers.get(requestid_header)
                if request_id:
                    # Capped at 200 to protect against malicious clients
                    # sending very large headers.
                    g.request_id = request_id[:200]

        # If installed register the Flask-DebugToolbar extension
        try:
            from flask_debugtoolbar import DebugToolbarExtension

            app.extensions["flask-debugtoolbar"] = DebugToolbarExtension(app)
        except ImportError:
            app.logger.debug("Flask-DebugToolbar extension not installed.")

        # Add theme template loader
        if app.config.get("APP_THEME"):
            app.jinja_env.loader = ThemeJinjaLoader(app, app.jinja_env.loader)

        # Register self
        app.extensions["invenio-app"] = self

    def init_config(self, app):
        """Initialize configuration.

        :param app: An instance of :class:`~flask.Flask`.
        """
        # RATELIMIT_STORAGE_URL was deprecated in 2.0 and removed in 3.0
        if "RATELIMIT_STORAGE_URL" in app.config:
            app.config["RATELIMIT_STORAGE_URI"] = app.config["RATELIMIT_STORAGE_URL"]
            warnings.warn(
                "RATELIMIT_STORAGE_URL has been renamed to RATELIMIT_STORAGE_URI.",
                DeprecationWarning,
            )

        config_apps = ["APP_", "RATELIMIT_"]
        flask_talisman_debug_mode = "'unsafe-inline'"
        for k in dir(config):
            if any([k.startswith(prefix) for prefix in config_apps]):
                app.config.setdefault(k, getattr(config, k))

        if app.config["DEBUG"]:
            app.config.setdefault("APP_DEFAULT_SECURE_HEADERS", {})
            headers = app.config["APP_DEFAULT_SECURE_HEADERS"]

            # ensure `content_security_policy` is not set to {}
            if headers.get("content_security_policy") != {}:
                headers.setdefault("content_security_policy", {})
                csp = headers["content_security_policy"]

                # ensure `default-src` is not set to []
                if csp.get("default-src") != []:
                    csp.setdefault("default-src", [])

                    # add default `content_security_policy` value when debug
                    if flask_talisman_debug_mode not in csp["default-src"]:
                        csp["default-src"].append(flask_talisman_debug_mode)
