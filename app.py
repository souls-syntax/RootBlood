import os
import subprocess
import threading
import time
from datetime import datetime, timezone, timedelta
import logging as log
import hashlib

import docker
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy

#-------------------------------------
# 1. Configuration
#-------------------------------------
# All the settings are defined here for easy management
# ------------------------------------

    
# Path to the shared "World" directory on host machine
BASE_PLAYGROUND_PATH = '/srv/playground'

# Name of the docker image we will be using.
DOCKER_IMAGE_NAME = 'chaospine:1.0.0'

# Path for helper script to make os users
UTILITY_USER_SCRIPT = 'path/to/user/script'

# database configuration
SQLALCHEMY_DB_PATH = 'sqlite:///memory.db'
SQLALCHEMY_TRACK_MODIFICATION = False

# Garbage collector configuration.
SESSION_IDLE_TTL_SECONDS = 72 * 3600
SESSION_ACTIVITY_CHECK_INTERVAL_SECONDS = 10 * 60

# Docker configuration
DOCKER = docker.from_env()

# Logging configuration
log.basicConfig(
    level=logging.INFO,  # or DEBUG, WARNING, ERROR, CRITICAL
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='app.log',  # optional: writes logs to a file
    filemode='a'         # append mode
)

# Port configuration
PORT_BEING_USED = '7681/tcp'

# ----------------------------------------------
# 2. DATABASE MODEL
# ----------------------------------------------
# Defines the database schema of the application
# ----------------------------------------------

# Define the app and initiate the DB
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATION'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    userhash = db.Column(db.String(80), unique=True, nullable=False)

class Project(db.Model):
    """REPRESENT THE PUBLIC HOME DIRECTORY IN THE 'WORLD'..."""
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(200), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    owner = db.relationship('User', backref=db.backref('directories', lazy=True))

#----------------------------------------------
# We are discarding the contributer model for the better user experience by implementing the specific technology `git`.
#----------------------------------------------

# class Contribution(db.Model):
#     # Tracks the active contribution workspace
#     id = db.Column(db.String(32), primary_key=True)
#     project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
#     contributor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     volume_name = db.Column(db.String(256), unique=True, nullable=False)
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
#

#----------------------------------------------
# Currently no implementing the garbage collector for completion of prototype model.
#----------------------------------------------

class ActiveSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    container_id = db.Column(db.String(64), unique=True, nullable=False)
    container_name = db.Column(db.String(128), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    last_active = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

#---------------------------------------------
# Defining user session
#---------------------------------------------

class UserManager:

    def __init__(self, userhash):
        self.userhash = userhash
    
    def starts_user_session(self):
        container_name = f"rootblood_session_{self.userhash}"
        volume_name = f"home_{self.userhash}"

        try:
            container = DOCKER.containers.get(container_name)

            if container.status != 'running':
                    log.info(f"Found stopped container for {self.userhash}. Starting it....")
                    container.start()
            else:
                    log.info(f"Container for {self.userhash} is already running....")
        except docker.errors.NotFound:
            log.info(f"No container found for {self.userhash}. Creating a new one...")
            DOCKER.containers.run(
                DOCKER_IMAGE_NAME,
                detach=True,
                name=container_name,
                volumes={volume_name:{'bind':f'/home/{self.userhash}', 'mode':'rw'},
                         BASE_PLAYGROUND_PATH:{'bind':'/global/','mode':'rw'}},
                ports={PORT_BEING_USED: None},
                working_dir=f'/home/{self.userhash}',
                stdin_open=True,
                tty=True
            )
            container = DOCKER.containers.get(container_name)
        
        except Exception as e:
            log.error(f"{e}")
        # TODO: Will need to write code for tracking the container here.
        # TODO: Will need to write the tarck_session(container) function

        host_port = container.ports[PORT_BEING_USED][0]['HostPort']
        return {"session_url":f"http://127.0.0.1:{host_port}", "container_name":container_name}


class ClaimDirectory:
    def __init__(self, userhash):
        self.userhash = userhash
    
    def claim_directory(self):
        
        user_base = os.path.join(BASE_PLAYGROUND_PATH, self.userhash)

        os.makedirs(user_base, exist_ok=True)

        try:
            uid = pwd.getpwnam(self.userhash).pw_uid
            gid = grp.getgrnam(self.userhash).gr_uid
            os.chown(user_base, uid, gid)
            os.chmod(user_base, 0o740)
        except KeyError:
            log.error("Key error happend inside the ClaimDirectory class")
        except PermissionError:
            log.error("permissionError happened")
            log.error("App is not running as sudo or don't have enough previlage to make user and such")
        except Exception as e:
            log.error(f"Error: {e}")
        
        return user_base


@app.route('/status')
def status():
    return jsonify({"status": "ok"})

@app.route('/session', methods=['POST'])
def create_session(username = None):
    log.info("Running the session endpoint")
    
    data = request.get_json() or {}
    
    try:
        if username == None:
            username = data.get('username')

    if not username:
        return jsonify({"Error": "Username is rewuired.."}), 400

    userhash = str(int(hashlib.sha256(username.encode('utf-8')).hexdigest(), 16) % 10**8)
    
    new_user = User(username=username,userhash=userhash)
    db.session.add(new_user)
    db.session.commit()


    project_dir = ClaimDirectory(userhash).claim_directory()
    new_project = Project(path=project_dir)

    result = UserManager.starts_user_session(userhash)

    return jsonify(result)

    

