from app import token
from app import mongo
from app.util import serialize_doc, get_manager_profile,load_weekly_notes
from flask import (
    Blueprint, flash, jsonify, abort, request
)
import dateutil.parser
from bson.objectid import ObjectId
from app.util import slack_message, slack_msg
from slackclient import SlackClient
import requests


from app.util import get_manager_juniors
from app.util import load_token,load_weekly_report_mesg
import datetime


from flask_jwt_extended import (
    JWTManager, jwt_required, create_access_token,
    get_jwt_identity, get_current_user, jwt_refresh_token_required,
    verify_jwt_in_request
)

bp = Blueprint('report', __name__, url_prefix='/')




@bp.route('/slack', methods=["GET"])
@jwt_required
def slack():
    current_user = get_current_user()
    slack = current_user['slack_id']
    token = load_token()
    sc = SlackClient(token)
    data = sc.api_call(
        "users.conversations",
        types = "private_channel",
        user = slack,
        exclude_archived=True
    )
    data_list = sc.api_call(
       "groups.list",
       exclude_archived=True
    )
    channel = []
    
        
    detail = data_list['groups']

    for ret in detail:
        if slack in ret['members']:
            channel.append({'value': ret['id'], 'text': ret['name']})
    inner =[]            
        
    element = data['channels']
    
    for dab in element:
        inner.append({'value': dab['id'], 'text': dab['name']})
        
    total = inner + channel
    result = []

    for elem in total:
        notSame = True
        for dec in result:
            if ((elem["text"] == dec["text"]) and (elem["value"] == dec["value"])):
                notSame =False
        if (notSame):
            result.append(elem)
    return jsonify(result)

@bp.route('/checkin', methods=["POST"])
@jwt_required
def add_checkin():
    if not request.json:
        abort(500)

    report = request.json.get("report", None)
    slackReport = request.json.get("slackReport", None)
    task_completed = request.json.get("task_completed", False)
    task_not_completed_reason = request.json.get(
        "task_not_completed_reason", "")
    highlight = request.json.get("highlight", "")
    date = request.json.get("date", "")
    highlight_task_reason = request.json.get("highlight_task_reason", None)
    today = datetime.datetime.utcnow()
    slackChannels = request.json.get("slackChannels", [])

    if not report:
          return jsonify({"msg": "Invalid Request"}), 400

    if task_completed == 1:
        task_completed = True
    else:
        task_completed = False

    current_user = get_current_user()
    username = current_user['username']
    slack = current_user['slack_id']

    if date is None:
        date_time = datetime.datetime.utcnow()
        formatted_date = date_time.strftime("%d-%B-%Y")
        rep = mongo.db.reports.find_one({
            "user": str(current_user["_id"]),
            "type": "daily",
            "created_at": {
                "$gte": datetime.datetime(today.year, today.month, today.day)
            }
        })
        if rep is not None:
            ret = mongo.db.reports.update({
                "user": str(current_user["_id"]),
                "type": "daily",
                "created_at": {
                    "$gte": datetime.datetime(today.year, today.month, today.day)
                }
            }, {
                "$set": {
                    "report": report,
                    "task_completed": task_completed,
                    "task_not_completed_reason": task_not_completed_reason,
                    "highlight": highlight,
                    "highlight_task_reason": highlight_task_reason,
                    "user": str(current_user["_id"]),
                    "created_at": date_time,
                    "username": current_user['username'],
                    "type": "daily"
                }})
            if len(highlight) > 0:
                slack_msg(channel=slackChannels,
                          msg="<@" + slack + ">!" + "\n" + "Report: " + "\n" + slackReport + "" + "\n"
                              + "Highlight: " + highlight)
            else:
                slack_msg(channel=slackChannels,
                          msg="<@" + slack + ">!" + "\n" + "Report: " + "\n" + slackReport + "")
        else:
            ret = mongo.db.reports.insert_one({
                "report": report,
                "task_completed": task_completed,
                "task_not_completed_reason": task_not_completed_reason,
                "highlight": highlight,
                "highlight_task_reason": highlight_task_reason,
                "user": str(current_user["_id"]),
                "created_at": date_time,
                "username": current_user['username'],
                "type": "daily"
            }).inserted_id

            docs = mongo.db.recent_activity.update({
                "user": str(current_user["_id"])},
                {"$push": {"Daily_checkin": {
                    "created_at": date_time,
                    "priority": 0,
                    "Daily_chechkin_message": date_time
                }}}, upsert=True)
            slack_message(msg="<@" + slack + ">!" + ' ''have created daily chechk-in at' + ' ' + str(formatted_date))
            if len(highlight) > 0:
                slack_msg(channel=slackChannels,
                          msg="<@" + slack + ">!" + "\n" + "Report: " + "\n" + slackReport + "" + "\n"
                              + "Highlight: " + highlight)
            else:
                slack_msg(channel=slackChannels,
                          msg="<@" + slack + ">!" + "\n" + "Report: " + "\n" + slackReport + "")
        return jsonify(str(ret))
    else:
        date_time = datetime.datetime.strptime(date, "%Y-%m-%d")
        sap = mongo.db.reports.insert_one({
            "report": report,
            "task_completed": task_completed,
            "task_not_completed_reason": task_not_completed_reason,
            "highlight": highlight,
            "highlight_task_reason": highlight_task_reason,
            "user": str(current_user["_id"]),
            "created_at": date_time,
            "username": current_user['username'],
            "type": "daily"
        }).inserted_id
        users = mongo.db.users.update({
            "_id": ObjectId(str(current_user['_id']))},
            {"$pull": {"missed_checkin_dates": {
                "date": date,
            }}})
        docs = mongo.db.recent_activity.update({
            "user": str(current_user["_id"])},
            {"$push": {"Daily_checkin": {
                "created_at": datetime.datetime.utcnow(),
                "priority": 0,
                "Daily_chechkin_message": date_time
            }}}, upsert=True)

        return jsonify(str(sap))



@bp.route('/reports', methods=["GET"])
@jwt_required
def checkin_reports():
    current_user = get_current_user()
    today = datetime.datetime.utcnow()
    last_monday = today - datetime.timedelta(days=today.weekday())
    docs = mongo.db.reports.find({
        "user": str(current_user["_id"]),
        "type": "daily",
        "created_at": {
            "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day)
        }
    }).sort("created_at", 1)
    docs = [serialize_doc(doc) for doc in docs]
    return jsonify(docs), 200


@bp.route('/delete/<string:checkin_id>', methods=['DELETE'])
@jwt_required
def delete_checkkin(checkin_id):
    current_user = get_current_user()
    docs = mongo.db.reports.remove({
        "_id": ObjectId(checkin_id),
        "type": "daily",
        "user": str(current_user['_id'])
    })
    return jsonify(str(docs))


@bp.route('/week_checkin', methods=["GET"])
@jwt_required
def week_checkin_reports():
    today = datetime.datetime.today()
    last_sunday = today - datetime.timedelta(days=(today.weekday() + 1))
    last_monday = today - datetime.timedelta(days=(today.weekday() + 8))
    current_user = get_current_user()
    docs = mongo.db.reports.find({
        "user": str(current_user["_id"]),
        "type": "daily",
        "created_at": {
            "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day),
            "$lte": datetime.datetime(last_sunday.year, last_sunday.month, last_sunday.day)
        }
    }).sort("created_at", 1)
    docs = [serialize_doc(doc) for doc in docs]
    return jsonify(docs), 200

    
@bp.route('/revoke_checkin', methods=["GET"])
@jwt_required
def revoke_checkin_reports():
    current_user = get_current_user()
    date_t=current_user["revoke"]
    today = date_t
    last_sunday = today - datetime.timedelta(days=(today.weekday() + 1))
    last_monday = today - datetime.timedelta(days=(today.weekday() + 8))
    current_user = get_current_user()
    docs = mongo.db.reports.find({
        "user": str(current_user["_id"]),
        "type": "daily",
        "created_at": {
            "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day),
            "$lte": datetime.datetime(last_sunday.year, last_sunday.month, last_sunday.day)
        }
    }).sort("created_at", 1)
    docs = [serialize_doc(doc) for doc in docs]
    return jsonify(docs), 200


@bp.route('/weekly_revoked/<string:weekly_id>', methods=["PUT"])
@jwt_required
def delete_weekly_checkin(weekly_id):
    created = request.json.get("created_at", None)
    user = request.json.get("user", None)
    datee=dateutil.parser.parse(created)
    use = mongo.db.users.update({
        "_id": ObjectId(user)},
        {"$set":{
            "revoke":datee
        }
    },upsert=True)

    docs = mongo.db.reports.remove({
        "_id": ObjectId(weekly_id),
        "type": "weekly",
    })
    return jsonify(str(docs))



@bp.route('/week_reports', methods=["GET"])
@jwt_required
def get_week_reports():
    current_user = get_current_user()
    today = datetime.date.today()
    last_sunday = today - datetime.timedelta(days=(today.weekday() + 1))
    last_monday = today - datetime.timedelta(days=(today.weekday() + 8))

    docs = mongo.db.reports.find({
        "user": str(current_user["_id"]),
        "type": "weekly",
        "created_at": {
            "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day),
            "$lte": datetime.datetime(last_sunday.year, last_sunday.month, last_sunday.day)
        }
    }).sort("created_at", 1)
    docs = [serialize_doc(doc) for doc in docs]
    return jsonify(docs), 200



@bp.route('/weekly', methods=["POST", "GET"])
@jwt_required
def add_weekly_checkin():
    current_user = get_current_user()
    today = datetime.datetime.utcnow()
    formated_date = today.strftime("%d-%B-%Y")
    last_monday = today - datetime.timedelta(days=today.weekday())
    if request.method == "GET":
        docs = mongo.db.reports.find({
            "type": "weekly",
            "user": str(current_user["_id"]),
            "created_at": {
                "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day)}
        }).sort("created_at", 1)
        docs = [serialize_doc(doc) for doc in docs]
        return jsonify(docs), 200
    if not request.json:
        abort(500)

    k_highlight = request.json.get("k_highlight", None)
    extra = request.json.get("extra", "")
    select_days = request.json.get("select_days", [])
    difficulty = request.json.get("difficulty", 0)
    username = current_user['username']
    slack = current_user['slack_id']
 
    if not k_highlight and select_days:
        return jsonify({"msg": "Invalid Request"}), 400
    
    reviewed = False
    users = mongo.db.users.find({
        "_id": ObjectId(current_user["_id"])
    })
    users = [serialize_doc(doc) for doc in users]

    managers_data = []
    for data in users:
        for mData in data['managers']:
            mData['reviewed'] = reviewed
            managers_data.append(mData)

    if 'kpi_id' in users:
        kpi_doc = mongo.db.kpi.find_one({
            "_id": ObjectId(current_user['kpi_id'])
        })
        kpi_name = kpi_doc['kpi_json']
        era_name = kpi_doc['era_json']
    else:
        kpi_name = ""
        era_name = ""
        
    managers_name = []
    for elem in managers_data:
        managers_name.append({"Id":elem['_id']})    
    
    ret = mongo.db.reports.insert_one({
        "k_highlight": k_highlight,
        "extra": extra,
        "select_days": select_days,
        "user": str(current_user["_id"]),
        "created_at": datetime.datetime.utcnow(),
        "type": "weekly",
        "is_reviewed": managers_data,
        "cron_checkin": True,
        "cron_review_activity": False,
        "kpi_json": kpi_name,
        "era_json": era_name,
        "difficulty": difficulty
    }).inserted_id

    for element in managers_name:
        manager = element['Id']
        rec = mongo.db.recent_activity.update({
            "user": manager},
            {"$push": {
                "Junior_weekly": {
                    "created_at": datetime.datetime.now(),
                    "priority": 1,
                    "Message": str(username)+' '+"have created a weekly report please review it"
                }}}, upsert=True)

    slack_message(msg="<@"+slack+">!"+' ''have created weekly report at' + ' ' + str(formated_date))
    return jsonify(str(ret)), 200


@bp.route('/weekly_automated', methods=["POST"])
@jwt_required
def add_weekly_automated():
    current_user = get_current_user()
    today = datetime.datetime.utcnow()
    slack = current_user['slack_id']
    formated_date = today.strftime("%d-%B-%Y")
    last_monday = today - datetime.timedelta(days=today.weekday())
    state = mongo.db.schdulers_setting.find_one({
        "weekly_automated": {"$exists": True}
        }, {"weekly_automated": 1, '_id': 0})
    status = state['weekly_automated']
    if status == 1:
        docs = mongo.db.reports.find_one({
                "type": "weekly",
                "user": str(current_user["_id"]),
                "created_at": {
                    "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day)}
            })

        if not docs:
            reviewed = False
            users = mongo.db.users.find({
                "_id": ObjectId(current_user["_id"])
            })
            users = [serialize_doc(doc) for doc in users]
            managers_data = []
            for data in users:
                for mData in data['managers']:
                    mData['reviewed'] = reviewed
                    managers_data.append(mData)

            if 'kpi_id' in users:
                kpi_doc = mongo.db.kpi.find_one({
                    "_id": ObjectId(current_user['kpi_id'])
                })
                kpi_name = kpi_doc['kpi_json']
                era_name = kpi_doc['era_json']
            else:
                kpi_name = ""
                era_name = ""
                
            managers_name = []
            for elem in managers_data:
                managers_name.append({"Id":elem['_id']})
            last_monday = today - datetime.timedelta(days=(today.weekday() + 8))
            last_sunday = today - datetime.timedelta(days=(today.weekday() + 1))
            ret = mongo.db.reports.find_one({
                "user": str(current_user["_id"]),
                "type": "daily",
                "created_at": {
                    "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day),
                    "$lte": datetime.datetime(last_sunday.year, last_sunday.month, last_sunday.day)}
            })
            if ret:
                select_days = ret['_id']
                ret = mongo.db.reports.insert_one({
                    "k_highlight": [{"KpiEra": "NA", "description": "NA"}],
                    "extra": "NA",
                    "select_days":[str(select_days)],
                    "user": str(current_user["_id"]),
                    "created_at": datetime.datetime.utcnow(),
                    "type": "weekly",
                    "is_reviewed": managers_data,
                    "cron_checkin": True,
                    "cron_review_activity": False,      
                    "kpi_json": kpi_name,
                    "era_json": era_name,
                    "difficulty": 0
                }).inserted_id
                slack_message(msg="<@"+slack+">!"+' ''have created weekly report at' + ' ' + str(formated_date))
                return jsonify({"msg":"weekly report has been successfully submitted"}), 200
            else:
                return jsonify({"msg": "you don't have daily checkin to submit"}),403
        else:
            return jsonify({"msg": "You have already submitted weekly checkin for this week"}),403
    else:
        return jsonify({"msg": "This feature has been turned off by Admin"}),403













@bp.route('/delete_weekly/<string:weekly_id>', methods=['DELETE'])
@jwt_required
def delete_weekly(weekly_id):
    current_user = get_current_user()
    docs = mongo.db.reports.remove({
        "_id": ObjectId(weekly_id),
        "type": "weekly",
        "user": str(current_user['_id'])
    })
    return jsonify(str(docs))

def load_checkin(id):
    print("load checkin id")
    print(id)
    ret = mongo.db.reports.find_one({
        "_id": ObjectId(id)
    })
    if not ret:
        sap = mongo.db.archive_report.find_one({
            "_id": id
        })
        return serialize_doc(sap)
    else:
        return serialize_doc(ret)


def load_all_checkin(all_chekin):
    today = datetime.datetime.utcnow()
    last_monday = today - datetime.timedelta(days=(today.weekday() + 8))
    last_sunday = today - datetime.timedelta(days=(today.weekday() + 1))
    ret = mongo.db.reports.find({
        "user": all_chekin,
        "type": "daily",
        "created_at": {
            "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day),
            "$lte": datetime.datetime(last_sunday.year, last_sunday.month, last_sunday.day)}
    }).sort("created_at", 1)
    ret = [serialize_doc(doc) for doc in ret]
    return ret


def notes(selectdays):
    for id in selectdays:
        ret = mongo.db.reports.find_one({
        "_id": ObjectId(id)
        })
        if not ret:
            sap = mongo.db.archive_report.find_one({
                "_id": id
            }) 
            user = sap['user']
            today = sap['created_at']
        else:
            user = ret['user']
            today = ret['created_at']
        current_user = get_current_user()
        last_monday = today - datetime.timedelta(days=today.weekday())
        coming_monday = today + datetime.timedelta(days=-today.weekday(), weeks=1)
        print(last_monday)
        print(coming_monday)
        print(user)
        ret = mongo.db.weekly_notes.find({
            "junior_id": user,
            "manager_id": str(current_user['_id']),
            "created_at": {
                "$gte": last_monday,
                "$lt": coming_monday}
        })
        ret = [serialize_doc(doc) for doc in ret]
        return ret



def add_checkin_data(weekly_report):
    print("report whose select_days is to be found")
    print(weekly_report)
    select_days = weekly_report["select_days"]
    typ = type(select_days)
    if typ==str:
        print("lenn")
        select_days = [select_days]
    else: 
        select_days = select_days
    
    print(select_days)
    if select_days is None:
        print("under None loop")
        print("NONE LOOP")
        select_days = None
    else:
        print("ID FOUND LOOP")
        print("id found loop")
        note =(notes(select_days))
        select_days = [load_checkin(day) for day in select_days]
    print("data which is loaded")
    all_chekin = weekly_report['user']
    all_chekin = (load_all_checkin(all_chekin))
    weekly_report["select_days"] = select_days
    weekly_report['all_chekin'] = all_chekin
    weekly_report['note'] = note
    return weekly_report


@bp.route("/manager_weekly_all", methods=["GET"])
@jwt_required
@token.manager_required
def get_manager_weekly_list_all():
    today = datetime.datetime.utcnow()
    last_monday = today - datetime.timedelta(days=today.weekday())
    current_user = get_current_user()
    juniors = get_manager_juniors(current_user['_id'])
    repo=[]
    docss = mongo.db.reports.find({
        "type": "weekly",
        "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"])}},
        "created_at": {
            "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day),
        },
        "user": {
            "$in": juniors
        }
    }).sort("created_at", 1)
    docss = [add_checkin_data(serialize_doc(doc)) for doc in docss]
    for a in docss:
        repo.append(a)
    docs = mongo.db.reports.find({
        "type": "weekly",
        "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"]), "reviewed": False}},
        "user": {
            "$in": juniors
        }
    }).sort("created_at", 1)
    docs = [add_checkin_data(serialize_doc(doc)) for doc in docs]
    for b in docs:
        if b not in repo:
            repo.append(b)
    return jsonify(repo), 200


@bp.route("/manager_weekly", methods=["GET"])
@bp.route("/manager_weekly/<string:weekly_id>", methods=["POST"])
@jwt_required
@token.manager_required
def get_manager_weekly_list(weekly_id=None):
    mesg=load_weekly_report_mesg()
    current_user = get_current_user()
    manager_name = current_user['username']
    if request.method == "GET":
        juniors = get_manager_juniors(current_user['_id'])

        docs = mongo.db.reports.find({
            "type": "weekly",
            "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"]), "reviewed": False}},
            "user": {
                "$in": juniors
            }
        }).sort("created_at", 1)
        docs = [add_checkin_data(serialize_doc(doc)) for doc in docs]
        return jsonify(docs), 200
    else:
        if not request.json:
            abort(500)

        rating = request.json.get("rating", 0)
        comment = request.json.get("comment", None)

        if comment is None or weekly_id is None:
            return jsonify(msg="invalid request"), 500
        juniors = get_manager_juniors(current_user['_id'])

        dab = mongo.db.reports.find({
            "_id": ObjectId(weekly_id),
            "type": "weekly",
            "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"]), "reviewed": False}},
            "user": {
                "$in": juniors
            }
        }).sort("created_at", 1)
        dab = [add_checkin_data(serialize_doc(doc)) for doc in dab]
        for data in dab:
            ID = data['user']
            rap = mongo.db.users.find({
                "_id": ObjectId(str(ID))
            })
            rap = [serialize_doc(doc) for doc in rap]
            for dub in rap:
                junior_name = dub['username']
                slack = dub['slack_id']
                print(slack)
                manager = dub['managers']
                for a in manager:
                    if a['_id']==str(current_user["_id"]):
                        manager_weights=a['weight']
                        sap = mongo.db.reports.find({
                            "_id": ObjectId(weekly_id),
                            "review": {'$elemMatch': {"manager_id": str(current_user["_id"])},
                        }
                     })
                        sap = [serialize_doc(saps) for saps in sap]
                        if not sap:
                            ret = mongo.db.reports.update({
                                "_id": ObjectId(weekly_id)
                            }, {
                                "$push": {
                                    "review": {
                                        "rating": rating,
                                        "created_at": datetime.datetime.utcnow(),
                                        "comment": comment,
                                        "manager_id": str(current_user["_id"]),
                                        "manager_weight":manager_weights
                                    }
                                }
                            })

                            cron = mongo.db.reports.update({
                                "_id": ObjectId(weekly_id)
                                }, {
                                "$set": {
                                    "cron_checkin": True
                                }})


                            docs = mongo.db.reports.update({
                                "_id": ObjectId(weekly_id),
                                "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"]), "reviewed": False}},
                            }, {
                                "$set": {
                                    "is_reviewed.$.reviewed": True
                                }})
                            dec = mongo.db.recent_activity.update({
                                "user": str(ID)},
                                {"$push": {
                                    "report_reviewed": {
                                        "created_at": datetime.datetime.now(),
                                        "priority": 0,
                                        "Message": "Your weekly report has been reviewed by "" " + manager_name
                                    }}}, upsert=True)
                            mesgg=mesg.replace("Slack_id:", "<@" + slack + ">!")
                            messag=mesgg.replace(":Manager_name", " " + manager_name)
                            slack_message(msg=messag)
                            return jsonify(str(ret)), 200
                        else:
                            return jsonify(msg="Already reviewed this report"), 400
        
@bp.route('/week_reviewed_reports', methods=["GET"])
@jwt_required
def week_reviewed_reports():
    current_user = get_current_user()
    today = datetime.date.today()
    last_sunday = today - datetime.timedelta(days=(today.weekday() + 1))
    last_monday = today - datetime.timedelta(days=(today.weekday() + 8))

    docs = mongo.db.reports.find({
        "user": str(current_user["_id"]),
        "type": "weekly",
        "review": {"$exists": True},
        "created_at": {
            "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day)
            
        }
    }).sort("created_at", 1)
    docs = [add_checkin_data(serialize_doc(doc)) for doc in docs]
    return jsonify(docs), 200



    
@bp.route('/recent_activities', methods=['GET'])
@jwt_required
def recent_activity():
    current_user = get_current_user()
    ret = mongo.db.recent_activity.find({
        "user": str(current_user['_id'])
    })
    ret = [serialize_doc(ret) for ret in ret]
    return jsonify(ret)

def load_kpi(kpi_data):
    print(kpi_data)
    ret = mongo.db.kpi.find_one({
        "_id": ObjectId(kpi_data)
    })
    return serialize_doc(ret)


def add_kpi_data(kpi):
    if "kpi_id" in kpi:
        data = kpi["kpi_id"]
        kpi_data = (load_kpi(data))
        kpi['kpi_id'] = kpi_data
    else:
        kpi['kpi_id'] = ""
    return kpi


@bp.route('/managers_juniors', methods=['GET'])
@jwt_required
@token.manager_required
def manager_junior():
    current_user = get_current_user()
    users = mongo.db.users.find({
        "managers": {
            "$elemMatch": {"_id": str(current_user['_id'])}
           
        }, "status": "Enabled"
    }, {"profile": 0}).sort("created_at", 1)
    users = [add_kpi_data(serialize_doc(ret)) for ret in users]
    return jsonify(users)


def load_user(user):
    ret = mongo.db.users.find_one({
        "_id": ObjectId(user)
    },{"profile": 0})
    return serialize_doc(ret)


def add_user_data(user):
    user_data = user['user']
    user_data = (load_user(user_data))
    user['user'] = user_data
    return user


@bp.route('/juniors_chechkin', methods=['GET'])
@jwt_required
@token.manager_required
def junior_chechkin():
    current_user = get_current_user()
    users = mongo.db.users.find({
        "managers": {
            "$elemMatch": {"_id": str(current_user['_id'])}
        }
    }, {"profile": 0})
    users = [serialize_doc(ret) for ret in users]
    ID = []
    for data in users:
        ID.append(data['_id'])
    print(ID)
    reports = mongo.db.reports.find({
        "user": {"$in": ID},
        "type": "daily"
    }).sort("created_at", 1)
    reports = [add_user_data(serialize_doc(doc)) for doc in reports]
    return jsonify(reports)


def load_manager(manager):
    ret = mongo.db.users.find_one({
        "_id": manager
    },{"profile": 0})
    return serialize_doc(ret)


def add_manager_data(manager):
    for elem in manager['review']:
        elem['manager_id'] = load_manager(ObjectId(elem['manager_id']))
    return manager


#Api for juniours see manager review.
@bp.route('/junior_review_response', methods=["GET"])
@jwt_required
def junior_review_response():
   current_user = get_current_user()
   docs = mongo.db.reports.find({
       "user": str(current_user["_id"]),
       "type": "weekly",
       "review": {'$exists': True},
   }).sort("created_at", 1)
   docs = [add_manager_data(serialize_doc(doc)) for doc in docs]
   return jsonify(docs)


@bp.route('/employee_feedback', methods=['POST', 'GET'])
@jwt_required
def employee_feedback():
    today = datetime.datetime.utcnow()
    month = today.strftime("%B")
    current_user = get_current_user()
    user = str(current_user['_id'])
    if request.method == "GET":
        rep = mongo.db.reports.find({
            "user": user,
            "type": "feedback",
        })
        rep = [add_user_data(serialize_doc(doc)) for doc in rep]
        return jsonify(rep), 200
    else:
        if not request.json:
            abort(500)
        feedback = request.json.get("feedback", "")
        rep = mongo.db.reports.find_one({
            "user": user,
            "type": "feedback",
            "month": month,
        })
        if rep is not None:
            return jsonify({"msg": "You have already submitted feedback for this month"}), 409
        else:
            report = mongo.db.reports.insert_one({
                "feedback": feedback,
                "user": user,
                "month": month,
                "type": "feedback",
            }).inserted_id
            return jsonify(str(report)), 200


@bp.route('/admin_fb_reply', methods=['GET'])
@bp.route('/admin_fb_reply/<string:feedback_id>', methods=['POST'])
@jwt_required
@token.admin_required
def admin_reply(feedback_id=None):
    current_user = get_current_user()
    username = current_user['username']
    if 'profileImage' in current_user:
        profileImage = current_user['profileImage']
    else:
        profileImage = ""
    if request.method == "GET":
        rep = mongo.db.reports.find({
            "type": "feedback"
        })
        rep = [add_user_data(serialize_doc(ret)) for ret in rep]
        return jsonify(rep), 200
    else:
        if not request.json:
            abort(500)
        reply = request.json.get("reply", None)
        report = mongo.db.reports.update({
            "_id": ObjectId(feedback_id),
            "type": "feedback"
        }, {
            "$set": {
                "admin_response": {
                "Reply": reply,
                "username": username,
                "profileImage": profileImage
                }
            }
        })
        return jsonify(str(report)), 200

def load_details(data):
    user_data = data['user']
    user_data = (load_user(user_data))
    data['user'] = user_data
    if data['review'] is None:
        review_detail = None
    else:
        review_detail = data['review']
    for elem in review_detail:
            elem['manager_id'] = load_manager(ObjectId(elem['manager_id']))
    return data


def no_review(data):
    user_data = data['user']
    user_data = (load_user(user_data))
    data['user'] = user_data
    review_data = None
    data['review'] = review_data
    return data


@bp.route('/junior_weekly_report', methods=['GET'])
@jwt_required
@token.manager_required
def junior_weekly_report():
    current_user = get_current_user()
    users = mongo.db.users.find({
        "managers": {
            "$elemMatch": {"_id": str(current_user['_id'])}
        }
    }, {"profile": 0})
    users = [serialize_doc(ret) for ret in users]
    ID = []
    for data in users:
        ID.append(data['_id'])
    print(ID)
    reports = mongo.db.reports.find({
        "user": {"$in": ID},
        "type": "weekly",
        "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"]), "reviewed": False}}
    }).sort("created_at", 1)
    reports = [no_review(serialize_doc(doc)) for doc in reports]
    report = mongo.db.reports.find({
        "user": {"$in": ID},
        "type": "weekly",
        "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"]), "reviewed": True}}
    }).sort("created_at", 1)
    report = [load_details(serialize_doc(doc)) for doc in report]
    report_all = reports + report

    return jsonify(report_all)


@bp.route('/delete_manager_response/<string:weekly_id>', methods=['DELETE'])
@jwt_required
@token.manager_required
def delete_manager_response(weekly_id):
    current_user = get_current_user()
    today = datetime.datetime.utcnow()
    last_day = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    next_day = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    report = mongo.db.reports.find_one({
        "_id": ObjectId(weekly_id),
        "review": {'$elemMatch': {"manager_id": str(current_user["_id"]), "created_at": {
                    "$gte": last_day,
                    "$lte": next_day}}
        }})
    print(report)
    if report is not None:
        ret = mongo.db.reports.update({
            "_id": ObjectId(weekly_id)}
            , {
            "$pull": {
                "review": {
                    "manager_id": str(current_user["_id"]),
                    }
            }})
        docs = mongo.db.reports.update({
            "_id": ObjectId(weekly_id),
            "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"]), "reviewed": True}},
        }, {
            "$set": {
                "is_reviewed.$.reviewed": False
            }})
        return jsonify(str(docs)), 200
    else:
        return jsonify({"msg": "You can no longer delete your submitted report"}), 400


@bp.route('/skip_review/<string:weekly_id>', methods=['POST'])
@jwt_required
@token.manager_required
def skip_review(weekly_id):
    state = mongo.db.schdulers_setting.find_one({
        "skip_review": {"$exists": True}
    }, {"skip_review": 1, '_id': 0})
    status = state['skip_review']
    if status == 1:
        current_user = get_current_user()
        message=load_weekly_notes()
        name = current_user['username']
        #findng current user date of joining.
        doj = current_user['dateofjoining']
        today = datetime.datetime.utcnow()
        month = today.strftime("%B")
        #finding report by report id
        reason = request.json.get("reason",None)
        selected = request.json.get("selected",None)
        reports = mongo.db.reports.find({
            "_id": ObjectId(weekly_id),
            "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"])}
            }
        })
        reports = [serialize_doc(doc) for doc in reports]
        #finding all managers review status. is manager have done his review or not.
        review_check=[]
        for check in reports:
            user=check['user']
            reviewed_array = check['is_reviewed']
            for review in reviewed_array:
                review_check.append(review['reviewed'])
        
        users = mongo.db.users.find({
            "_id": ObjectId(user)
            })
        users = [serialize_doc(doc) for doc in users]
        for user_info in users:
            slack_id = user_info['slack_id']
            junior_name = user_info['username']
        #checking if a single manager have done his review then allow the user to skip his review.
        print("resonnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnn")
        print(reason)
        if selected=="b" or selected=="a":
            msg = "Weekly report is skipped by"+ ' '+name
        
        elif selected=="d":
            report = mongo.db.reports.insert_one({
                "feedback": "I am no longer associated in any project with "+ junior_name,
                "user": str(current_user["_id"]),
                "month": month,
                "type": "feedback",
            }).inserted_id
            msg = "Weekly report is skipped by"+ ' '+name
        else:
            msg = "Weekly report is skipped by"+' '+name+' '+"because"+' '+reason
        
        if 1 in review_check:
            rep = mongo.db.reports.update({
                    "_id": ObjectId(weekly_id)
                    }, {
                    "$push": {
                        "skip_reason":msg }
                    }, upsert=False)
        
            rep = mongo.db.reports.update({
                    "_id": ObjectId(weekly_id),
                    "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"])}},
                }, {
                    "$pull": {
                        "is_reviewed": {"_id": str(current_user["_id"])}
                    }}, upsert=False)
            
            missed_chec_mesg=message.replace("Slack_id:", "<@" + slack_id + ">!")    
            mesgg=missed_chec_mesg.replace(":Manager_name",""+name+"")
            slack_message(msg=mesgg)
            return jsonify({"status":"success"})
        else:
            #finding all assign managers_id
            manager_id = []
            for data in reports:
                for elem in data['is_reviewed']:
                    manager_id.append(ObjectId(elem['_id']))
            #finding all assign managers weights and current_manager weights
            manager_weight = []
            current_manag_weight=[]
            for manager_data in reports:
                for elem in manager_data['is_reviewed']:
                    manager_weight.append(elem['weight'])
                    if elem['_id'] == str(current_user["_id"]):
                        current_manag_weight.append(elem['weight'])
            #finding all mangers by id
            managers = mongo.db.users.find({
                "_id": {"$in": manager_id}
            })
            managers = [serialize_doc(doc) for doc in managers]
            #finding managers join date.
            join_date = []
            for dates in managers:
                join_date.append(dates['dateofjoining'])
        
            for weig in current_manag_weight:
                current_m_weight = weig
            no_of_time = manager_weight.count(current_m_weight)
            #checking if two managers have same weights.
            if no_of_time > 1:
                #checking that assign manager is greater then one or not if a single manager left then he can not skip report
                if len(join_date) > 1:
                    oldest = min(join_date)
                    if doj == oldest:
                        rep = mongo.db.reports.update({
                        "_id": ObjectId(weekly_id)
                        }, {
                        "$push": {
                            "skip_reason":msg }
                        }, upsert=False)    
                        
                        rep = mongo.db.reports.update({
                            "_id": ObjectId(weekly_id),
                            "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"])}},
                        }, {
                            "$pull": {
                                "is_reviewed": {"_id": str(current_user["_id"])}
                            }}, upsert=False)
                        missed_chec_mesg=message.replace("Slack_id:", "<@" + slack_id + ">!")    
                        mesgg=missed_chec_mesg.replace(":Manager_name",""+name+"")
                        slack_message(msg=mesgg)
                        return jsonify({"status":"success"})
                    else:
                        return jsonify({"msg": "Senior manager needs to give review before you can skip"}), 400
                else:
                    return jsonify({"msg": "You cannot skip this report review as you are the only manager"}), 400
            else:
                #checking that assign manager is greater then one or not if a single manager left then he can not skip report
                if len(manager_weight)>1:
                    #finding max weight in weight list
                    max_weight = max(manager_weight)
                    #if current manager weight is max then he can skip his review
                    if current_m_weight == max_weight:
                        rep = mongo.db.reports.update({
                        "_id": ObjectId(weekly_id)
                        }, {
                        "$push": {
                            "skip_reason":msg }
                        }, upsert=False)
                        
                        rep = mongo.db.reports.update({
                            "_id": ObjectId(weekly_id),
                            "is_reviewed": {'$elemMatch': {"_id": str(current_user["_id"])}},
                        }, {
                            "$pull": {
                                "is_reviewed": {"_id": str(current_user["_id"])}
                            }}, upsert=False)
                        missed_chec_mesg=message.replace("Slack_id:", "<@" + slack_id + ">!")    
                        mesgg=missed_chec_mesg.replace(":Manager_name",""+name+"")
                        slack_message(msg=mesgg)
                        return jsonify({"status":"success"})
                    else:
                        return jsonify({"msg": "Manager with higher weight needs to give review before you can skip"}), 400
                else:
                    return jsonify({"msg": "You cannot skip this report review as you are the only manager"}), 400        
    else:
        return jsonify({"msg": "Admin not allow to skip review"}), 400



#Api for add note in weekly
@bp.route('/review_note', methods=['POST'])
@jwt_required
@token.manager_required
def review_note():
    current_user = get_current_user()
    comment = request.json.get("comment",None)
    junior_id = request.json.get("junior_id",None)
    ret = mongo.db.weekly_notes.insert_one({
                "comment":comment,
                "manager_id":str(current_user['_id']),
                "junior_id":junior_id,
                "created_at":datetime.datetime.utcnow(),
                "type":"weekly_note"
            }).inserted_id
    return jsonify({"status":"success"})
                        

#Api for get notes which add on junior report. 
@bp.route('/review_note/get_review', methods=['GET'])
@jwt_required
@token.manager_required
def review_note_get():
    current_user = get_current_user()
    today = datetime.datetime.utcnow()
    last_monday = today - datetime.timedelta(days=today.weekday())
    rev = mongo.db.weekly_notes.find({
        "manager_id":str(current_user["_id"]),
        "created_at": {
                "$gte": datetime.datetime(last_monday.year, last_monday.month, last_monday.day)
                }
        })
    rev = [serialize_doc(doc) for doc in rev]
    return jsonify(rev)



#Api for delete or update notes
@bp.route('/review_note/delete_review/<string:note_id>', methods=['DELETE','PUT'])
@jwt_required
@token.manager_required
def review_note_update(note_id):
    current_user = get_current_user()
    if request.method == "DELETE":    
        docs = mongo.db.weekly_notes.remove({
            "_id": ObjectId(note_id),
            "manager_id": str(current_user['_id']),
        })
        return jsonify({"status":"success"}), 200    
    if request.method == "PUT":
        comment = request.json.get("comment",None)
        junior_id = request.json.get("junior_id",None)
        rep = mongo.db.weekly_notes.update({
                "_id":ObjectId(note_id),
                    }, {
                    "$set": {
                        "comment":comment,
                        "manager_id":str(current_user['_id']),
                        "junior_id":junior_id,
                        "updated_at":datetime.datetime.utcnow(),
                        "type":"weekly_note"
                         }
                    },upsert=True)
        return jsonify({"status":"success"}), 200
