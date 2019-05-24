from flask import Blueprint, request, render_template, \
    flash, g, session, redirect, url_for

from app.utils.db_models import db
from flask_basicauth import BasicAuth
from authlib.client import OAuth2Session
from utils.search_console import get_search_terms

from app.auth.models import User as UserModel
from config import settings

import flask
import functools
import os
import google.oauth2.credentials
import googleapiclient.discovery

ACCESS_TOKEN_URI = settings.ACCESS_TOKEN_URI
AUTHORIZATION_URL = settings.AUTHORIZATION_URL
AUTHORIZATION_SCOPE = settings.AUTHORIZATION_SCOPE
OAUTH_SCOPE = settings.OAUTH_SCOPE
AUTH_REDIRECT_URI = settings.AUTH_REDIRECT_URI
BASE_URI = settings.BASE_URI
CLIENT_ID = settings.CLIENT_ID
CLIENT_SECRET = settings.CLIENT_SECRET
AUTH_TOKEN_KEY = settings.AUTH_TOKEN_KEY
AUTH_STATE_KEY = settings.AUTH_STATE_KEY

google_auth = Blueprint('google_auth', __name__, url_prefix='/google')


def is_logged_in():
    return True if AUTH_TOKEN_KEY in flask.session else False


def build_credentials():
    if not is_logged_in():
        raise Exception('User must be logged in')

    oauth2_tokens = flask.session[AUTH_TOKEN_KEY]

    return google.oauth2.credentials.Credentials(
        oauth2_tokens['access_token'],
        refresh_token=oauth2_tokens['refresh_token'],
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri=ACCESS_TOKEN_URI)


def get_user_info():
    credentials = build_credentials()

    oauth2_client = googleapiclient.discovery.build(
        'oauth2', 'v2', credentials=credentials
    )

    return oauth2_client.userinfo().get().execute()


def no_cache(view):
    @functools.wraps(view)
    def no_cache_impl(*args, **kwargs):
        response = flask.make_response(view(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'  # noqa
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response

    return functools.update_wrapper(no_cache_impl, view)


def get_service():
    credentials = build_credentials()
    webmasters_service = googleapiclient.discovery.build(
        'webmasters', 'v3', credentials=credentials
    )
    return webmasters_service


@google_auth.route('/login')
# @no_cache
def login():
    session = OAuth2Session(CLIENT_ID, CLIENT_SECRET,
                            scope=AUTHORIZATION_SCOPE + OAUTH_SCOPE,
                            redirect_uri=AUTH_REDIRECT_URI)

    uri, state = session.authorization_url(AUTHORIZATION_URL)

    flask.session[AUTH_STATE_KEY] = state
    flask.session.permanent = True

    return flask.redirect(uri, code=302)


@google_auth.route('/auth')
# @no_cache
def google_auth_redirect():
    req_state = request.args.get('state', default=None, type=None)

    if req_state != flask.session[AUTH_STATE_KEY]:
        response = flask.make_response('Invalid state parameter', 401)
        return response

    session = OAuth2Session(CLIENT_ID, CLIENT_SECRET,
                            scope=AUTHORIZATION_SCOPE + OAUTH_SCOPE,
                            state=flask.session[AUTH_STATE_KEY],
                            redirect_uri=AUTH_REDIRECT_URI)

    oauth2_tokens = session.fetch_access_token(
        ACCESS_TOKEN_URI,
        authorization_response=request.url
    )

    flask.session[AUTH_TOKEN_KEY] = oauth2_tokens

    user_info = get_user_info()
    users = UserModel.query.filter_by(email=user_info['email']).all()

    user = {
        "name": user_info['name'],
        "family_name": user_info['family_name'],
        "picture": user_info['picture'],
        "locale": user_info['locale'],
        "email": user_info['email'],
        "given_name": user_info['given_name'],
        "id": user_info['id'],
        "verified_email": user_info['verified_email'],
        "role": 0
    }

    if len(users) < 1:
        user = UserModel(user)
        db.session.add(user)
        db.session.commit()
    else:
        print('This user exist already')

    service = get_service()
    get_sitemaps(webmasters_service=service)
    get_search_terms(service=service, property_uri="https://celebrationsaunas.com")  # noqa

    return flask.redirect(BASE_URI, code=302)


@google_auth.route('/logout')
# @no_cache
def logout():
    flask.session.pop(AUTH_TOKEN_KEY, None)
    flask.session.pop(AUTH_STATE_KEY, None)

    return flask.redirect(BASE_URI, code=302)
