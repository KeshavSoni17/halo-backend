from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
from app.config import settings
from app.services.utils import encrypt, decrypt, hash_password

class database:
    def __init__(self):
        self.client = MongoClient(settings.MONGODB_URL)
        self.database = self.client['database']
        self.sessions = self.database['sessions']
        self.users = self.database['users']
        self.templates = self.database['templates']
        self.visits = self.database['visits']
    
    def create_session(self, user_id):
        session = {
            'user_id': user_id,
            'expiration_date': datetime.utcnow() + timedelta(days=1),
        }
        self.sessions.insert_one(session)
        if session:
            session['session_id'] = str(session['_id'])
            session['user_id'] = str(session['user_id'])
            session['expiration_date'] = str(session['expiration_date'])
            del session['_id']
        return session

    def get_session(self, session_id):
        session = self.sessions.find_one({'_id': ObjectId(session_id)})
        if session:
            session['session_id'] = str(session['_id'])
            session['user_id'] = str(session['user_id'])
            session['expiration_date'] = str(session['expiration_date'])
            del session['_id']
        return session
    
    def is_session_valid(self, session_id):
        session = self.get_session(session_id)
        if session:
            if datetime.fromisoformat(session['expiration_date'].replace('Z', '+00:00')) > datetime.utcnow():
                return session['user_id']
        return None

    def delete_session(self, session_id):
        self.sessions.delete_one({'_id': ObjectId(session_id)})

    def decrypt_user(self, user):
        user['user_id'] = str(user['_id'])
        user['visit_ids'] = [str(visit_id) for visit_id in user['visit_ids']]
        user['template_ids'] = [str(template_id) for template_id in user['template_ids']]
        user['name'] = decrypt(user['encrypt_name'])
        user['email'] = decrypt(user['encrypt_email'])
        user['created_at'] = str(user['created_at'])
        user['modified_at'] = str(user['modified_at'])
        del user['_id']
        del user['encrypt_name']
        del user['encrypt_email']
        return user
    
    def create_user(self, name, email, password):
        users = self.users.find({})
        for user in users:
            if 'encrypt_email' in user and decrypt(user['encrypt_email']) == email:
                return None
                
        default_templates = list(self.templates.find({'status': 'DEFAULT'}))
        default_template_ids = [template['_id'] for template in default_templates]
        default_template_id = str(default_templates[0]['_id']) if default_templates else ''
                
        user = {
            'created_at': datetime.utcnow(),
            'modified_at': datetime.utcnow(),
            'status': 'ACTIVE',
            'encrypt_name': encrypt(name),
            'encrypt_email': encrypt(email),
            'hash_password': hash_password(password),
            'user_specialty': '',
            'default_template_id': default_template_id,
            'default_language': 'en',
            'template_ids': default_template_ids,
            'visit_ids': [],
            'daily_statistics': {
            }
        }
        self.users.insert_one(user)

        return self.decrypt_user(user)
        
    
    def update_user(self, user_id, name=None, email=None, password=None, user_specialty=None, default_template_id=None, default_language=None, template_ids=None, visit_ids=None):
        update_fields = {}
        if name is not None:
            update_fields['encrypt_name'] = encrypt(name)
        if email is not None:
            update_fields['encrypt_email'] = encrypt(email)
        if password is not None:
            update_fields['hash_password'] = hash_password(password)
        if default_template_id is not None:
            update_fields['default_template_id'] = default_template_id
        if default_language is not None:
            update_fields['default_language'] = default_language
        if user_specialty is not None:
            update_fields['user_specialty'] = user_specialty
        if template_ids is not None:
            update_fields['template_ids'] = template_ids
        if visit_ids is not None:
            update_fields['visit_ids'] = visit_ids
            
        if update_fields:
            update_fields['modified_at'] = datetime.utcnow()
            self.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_fields})
        user = self.users.find_one({'_id': ObjectId(user_id)})

        return self.decrypt_user(user)
    
    def delete_user(self, user_id):
        self.users.delete_one({'_id': ObjectId(user_id)})
        return True
    
    def get_user(self, user_id):
        user = self.users.find_one({'_id': ObjectId(user_id)})
        return self.decrypt_user(user)
    
    def get_user_by_email(self, email):
        users = self.users.find({})
        for user in users:
            if 'encrypt_email' in user and decrypt(user['encrypt_email']) == email:
                return self.decrypt_user(user)
        return None
    
    def verify_user(self, email, password):
        users = self.users.find({})
        for user in users:
            if 'encrypt_email' in user and decrypt(user['encrypt_email']) == email:
                if user['hash_password'] == hash_password(password):
                    return self.decrypt_user(user)
                return None
        return None
    
    def get_user_templates(self, user_id):
        try:
            user = self.get_user(user_id)
            template_ids = [ObjectId(tid) for tid in user['template_ids']]
            templates = list(self.templates.find({'_id': {'$in': template_ids}}))
            return [self.decrypt_template(template) for template in templates]
        except Exception as e:
            return []
    
    def get_user_visits(self, user_id):
        try:
            user = self.get_user(user_id)
            visit_ids = [ObjectId(vid) for vid in user['visit_ids']]
            visits = list(self.visits.find({'_id': {'$in': visit_ids}}))
            return [self.decrypt_visit(visit) for visit in visits]
        except Exception as e:
            return []
        
    def decrypt_template(self, template):
        template['template_id'] = str(template['_id'])
        template['user_id'] = str(template['user_id'])
        template['created_at'] = str(template['created_at'])
        template['modified_at'] = str(template['modified_at'])
        template['name'] = decrypt(template['encrypt_name'])
        template['instructions'] = decrypt(template['encrypt_instructions'])
        template['print'] = decrypt(template['encrypt_print'])
        if 'encrypt_header' in template:
            template['header'] = decrypt(template['encrypt_header'])
        if 'encrypt_footer' in template:
            template['footer'] = decrypt(template['encrypt_footer'])
        del template['_id']
        del template['encrypt_name']
        del template['encrypt_instructions']
        if 'encrypt_header' in template:
            del template['encrypt_header']
        if 'encrypt_footer' in template:
            del template['encrypt_footer']
        return template
    
    def create_template(self, user_id):
        user = self.get_user(user_id)
        template = {
            'user_id': user_id,
            'created_at': datetime.utcnow(),
            'modified_at': datetime.utcnow(),
            'status': 'READY',
            'encrypt_name': encrypt('New Template'),
            'encrypt_instructions': encrypt(''),
            'encrypt_print': encrypt(''),
            'encrypt_header': encrypt(''),
            'encrypt_footer': encrypt(''),
        }
        self.templates.insert_one(template)
        user['template_ids'].append(template['_id'])
        self.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'template_ids': user['template_ids']}})

        return self.decrypt_template(template)

    def update_template(self, template_id, name=None, instructions=None, print=None, header=None, footer=None):
        update_fields = {}
        if name is not None:
            update_fields['encrypt_name'] = encrypt(name)
        if instructions is not None:
            update_fields['encrypt_instructions'] = encrypt(instructions)
        if print is not None:
            update_fields['encrypt_print'] = encrypt(print)  
        if header is not None:
            update_fields['encrypt_header'] = encrypt(header)
        if footer is not None:
            update_fields['encrypt_footer'] = encrypt(footer)
        
        if instructions is not None:
            update_fields['modified_at'] = datetime.utcnow()
            
        if update_fields:
            self.templates.update_one({'_id': ObjectId(template_id)}, {'$set': update_fields})
        template = self.templates.find_one({'_id': ObjectId(template_id)})
        
        return self.decrypt_template(template)
    def delete_template(self, template_id, user_id):
        user = self.get_user(user_id)
        user['template_ids'].remove(template_id)
        self.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'template_ids': user['template_ids']}})
        self.templates.delete_one({'_id': ObjectId(template_id)})
        return True

    def get_template(self, template_id):
        template = self.templates.find_one({'_id': ObjectId(template_id)})
        return self.decrypt_template(template)
    
    def decrypt_visit(self, visit):
        visit['visit_id'] = str(visit['_id'])
        visit['user_id'] = str(visit['user_id'])
        visit['created_at'] = str(visit['created_at'])
        visit['modified_at'] = str(visit['modified_at'])
        if visit['template_modified_at']:
            visit['template_modified_at'] = str(visit['template_modified_at'])
        if visit['recording_started_at']:
            visit['recording_started_at'] = str(visit['recording_started_at'])
        if visit['recording_finished_at']:
            visit['recording_finished_at'] = str(visit['recording_finished_at'])
        visit['name'] = decrypt(visit['encrypt_name'])
        visit['additional_context'] = decrypt(visit['encrypt_additional_context'])
        visit['transcript'] = decrypt(visit['encrypt_transcript'])
        visit['note'] = decrypt(visit['encrypt_note'])
        del visit['_id']
        del visit['encrypt_name']
        del visit['encrypt_additional_context']
        del visit['encrypt_transcript']
        del visit['encrypt_note']
        return visit
    
    def create_visit(self, user_id):
        user = self.get_user(user_id)
        visit = {
            'user_id': user_id,
            'created_at': datetime.utcnow(),
            'modified_at': datetime.utcnow(),
            'status': 'NOT_STARTED',
            'encrypt_name': encrypt('New Visit'),
            'template_modified_at': datetime.utcnow(),
            'template_id': user['default_template_id'],
            'language': user['default_language'],
            'encrypt_additional_context': encrypt(''),
            'recording_started_at': '',
            'recording_duration': '',
            'recording_finished_at': '',
            'encrypt_transcript': encrypt(''),
            'encrypt_note': encrypt(''),
           
        }
        self.visits.insert_one(visit)

        user['visit_ids'].append(visit['_id'])
        self.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'visit_ids': user['visit_ids']}})
        
        self.update_daily_statistic(user_id, 'visits', 1)

        return self.decrypt_visit(visit)
    
    def update_visit(self, visit_id, status=None, name=None, template_modified_at=None, template_id=None, language=None, additional_context=None, recording_started_at=None, recording_duration=None, recording_finished_at=None, transcript=None, note=None):
        update_fields = {}
        if status is not None:
            update_fields['status'] = status
        if name is not None:
            update_fields['encrypt_name'] = encrypt(name)
        if template_modified_at is not None:
            update_fields['template_modified_at'] = template_modified_at
        if template_id is not None:
            update_fields['template_id'] = template_id
        if language is not None:
            update_fields['language'] = language
        if additional_context is not None:
            update_fields['encrypt_additional_context'] = encrypt(additional_context)
        if recording_started_at is not None:
            update_fields['recording_started_at'] = recording_started_at
        if recording_duration is not None:
            current_visit = self.visits.find_one({'_id': ObjectId(visit_id)})
            duration_increment = max(0, float(recording_duration or 0) - float(current_visit.get('recording_duration', 0) or 0))
            if duration_increment > 0:
                self.update_daily_statistic(str(current_visit['user_id']), 'audio_time', duration_increment)
            update_fields['recording_duration'] = recording_duration
        if recording_finished_at is not None:
            update_fields['recording_finished_at'] = recording_finished_at
        if transcript is not None:
            update_fields['encrypt_transcript'] = encrypt(transcript)
        if note is not None:
            update_fields['encrypt_note'] = encrypt(note)

        if update_fields:
            update_fields['modified_at'] = datetime.utcnow()
            self.visits.update_one({'_id': ObjectId(visit_id)}, {'$set': update_fields})
        visit = self.visits.find_one({'_id': ObjectId(visit_id)})
        
        return self.decrypt_visit(visit)

    def delete_visit(self, visit_id, user_id):
        user = self.get_user(user_id)
        user['visit_ids'].remove(visit_id)
        self.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'visit_ids': user['visit_ids']}})
        self.visits.delete_one({'_id': ObjectId(visit_id)})
        return True

    def get_visit(self, visit_id):
        visit = self.visits.find_one({'_id': ObjectId(visit_id)})
        return self.decrypt_visit(visit)

    def create_default_template(self, name,  instructions, print='', header='', footer=''):
        template = {
            'user_id': 'HALO',
            'created_at': datetime.utcnow(),
            'modified_at': datetime.utcnow(),
            'status': 'DEFAULT',
            'encrypt_name': encrypt(name),
            'encrypt_instructions': encrypt(instructions),
            'encrypt_print': encrypt(print),
            'encrypt_header': encrypt(header),
            'encrypt_footer': encrypt(footer),
        }
        self.templates.insert_one(template)

        users = self.users.find({})
        for user in users:
            user['template_ids'].append(template['_id'])
            self.users.update_one({'_id': ObjectId(user['_id'])}, {'$set': {'template_ids': user['template_ids']}})
        return self.decrypt_template(template)
    
    def get_default_template(self, template_id):
        template = self.templates.find_one({'_id': ObjectId(template_id)})
        return self.decrypt_template(template)
        
    def delete_default_template(self, template_id):
        self.templates.delete_one({'_id': ObjectId(template_id)})
        users = self.users.find({})
        for user in users:
            if template_id in user['template_ids']:
                user['template_ids'].remove(template_id)
                self.users.update_one({'_id': ObjectId(user['_id'])}, {'$set': {'template_ids': user['template_ids']}})
        return True

    def update_daily_statistic(self, user_id, stat_type, value):
        user = self.users.find_one({'_id': ObjectId(user_id)})
        if not user:
            return
            
        today = datetime.utcnow().strftime('%Y-%m-%d')
        daily_statistics = user.get('daily_statistics', {})
        
        if today not in daily_statistics:
            daily_statistics[today] = {
                'visits': 0,
                'audio_time': 0
            }
            
        if stat_type == 'visits':
            daily_statistics[today]['visits'] += 1
        elif stat_type == 'audio_time':
            if isinstance(value, str):
                try:
                    value = float(value)
                except ValueError:
                    value = 0
            
            daily_statistics[today]['audio_time'] += value
            
        self.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'daily_statistics': daily_statistics}}
        )