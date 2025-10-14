import os
import subprocess
import threading
import time
from datetime import datetime, timezone, timedelta

import docker
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy

#-------------------------------------
# 1. Configuration
#-------------------------------------
# All the settings are defined here for easy management

class Config:
    
    # Path to the shared "World" directory on host machine
    BASE_PLAYGROUND_PATH = 'srv/playground'
    # Name of the docker image we will be using.
    DOCKER_IMAGE_NAME = 'chaospine:1.0.0'
    # Path for helper script to make os users
    UTILITY_USER_SCRIPT = 'path/to/user/script'
    #database configuration
    SQLALCHEMY_DB_PATH = 'sqlit:///memory.db'
    SQLALCHEMY_TRACK_MODIFICATION = False
    #Garbage collector configuration.
    SESSION_IDLE_TTL_SECONDS = 72 * 3600
    SESSION_ACTIVITY_CHECK_INTERVAL_SECONDS = 10 * 60

# ----------------------------------------------
# 2. DATABASE MODEL
# ----------------------------------------------
# Defines the database schema of the application
# ----------------------------------------------

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    username = db.Column(db.String(80), unique=True, nullable=False)

class Project(db.Model):
    """REPRESENT THE PUBLIC HOME DIRECTORY IN THE 'WORLD'..."""
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(200), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    owner = db.relationship('User', backref=db.backref('directories', lazy=True))

class Contribution(db.Model):
    # Tracks the active contribution workspace
    id = db.Column(db.String(32), primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    contributor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    volume_name = db.Column(db.String(256), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ActiveSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    container_id = db.Column(db.String(64), unique=True, nullable=False)
    container_name = db.Column(db.String(128), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    last_active = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    