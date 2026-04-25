import base64
import json
from urllib.parse import urlencode

import requests

US_BASE = "https://api.plaud.ai"
EU_BASE = "https://api-euc1.plaud.ai"

class PlaudAuthError(Exception):
	pass

class PlaudTokenExpiredError(PlaudAuthError):
	pass

def jwt_expiry_seconds(token):
	"""Return Unix-epoch-seconds expiry from a JWT, or 0 if unreadable."""
	if not token:
		return 0
	try:
		parts = token.split('.')
		if len(parts) != 3:
			return 0
		padded = parts[1] + '=' * (-len(parts[1]) % 4)
		payload = json.loads(base64.urlsafe_b64decode(padded))
		return int(payload.get('exp', 0))
	except Exception:
		return 0

class PlaudClient:
	def __init__(self, email=None, password=None, token=None, region='us', on_token_expired=None):
		"""on_token_expired: optional callable returning a fresh JWT string. Invoked
		when the API rejects the current token; the client retries the request
		once with the new token."""
		if not token and not (email and password):
			raise ValueError("Provide either token, or email+password")
		self.email = email
		self.password = password
		self.region = region
		self.token = token
		self.token_expires_at = jwt_expiry_seconds(token) * 1000 if token else 0
		self.on_token_expired = on_token_expired

	@property
	def base_url(self):
		return EU_BASE if self.region == 'eu' else US_BASE

	def login(self):
		body = urlencode({'username': self.email, 'password': self.password})
		res = requests.post(
			f"{self.base_url}/auth/access-token",
			data=body,
			headers={'Content-Type': 'application/x-www-form-urlencoded'},
			timeout=30,
		)
		data = res.json()
		if data.get('status') != 0 or not data.get('access_token'):
			raise PlaudAuthError(data.get('msg') or f"Login failed (status {data.get('status')})")
		self.token = data['access_token']
		self.token_expires_at = jwt_expiry_seconds(self.token) * 1000
		return self.token

	def _ensure_token(self):
		"""Guarantee a token exists before making a request. We don't check
		expiry here — the API tells us when a token is rejected, and we refresh
		reactively in _handle_auth_failure."""
		if self.token:
			return
		if self.email and self.password:
			self.login()
			return
		if self.on_token_expired:
			new_token = self.on_token_expired()
			if new_token:
				self.token = new_token
				self.token_expires_at = jwt_expiry_seconds(new_token) * 1000
				return
		raise PlaudAuthError("No token available and no way to obtain one.")

	def _request(self, path, method='GET', _retry=False, **kwargs):
		self._ensure_token()
		url = f"{self.base_url}{path}"
		headers = {'Authorization': f"Bearer {self.token}", 'Content-Type': 'application/json'}
		headers.update(kwargs.pop('headers', {}))
		res = requests.request(method, url, headers=headers, timeout=60, **kwargs)
		if res.status_code in (401, 403):
			return self._handle_auth_failure(path, method, _retry, **kwargs)
		res.raise_for_status()
		data = res.json()
		# API returns -302 with the correct region's domain when we hit the wrong region
		if data.get('status') == -302 and data.get('data', {}).get('domains', {}).get('api'):
			domain = data['data']['domains']['api']
			self.region = 'eu' if 'euc1' in domain else 'us'
			return self._request(path, method, _retry=_retry, **kwargs)
		# Some APIs return 200 with a body-level auth error code
		if data.get('status') in (-401, -403):
			return self._handle_auth_failure(path, method, _retry, **kwargs)
		return data

	def _handle_auth_failure(self, path, method, already_retried, **kwargs):
		if already_retried:
			raise PlaudTokenExpiredError("Token still rejected after refresh")
		if self.on_token_expired:
			new_token = self.on_token_expired()
			if not new_token:
				raise PlaudTokenExpiredError("Refresh callback returned no token")
			self.token = new_token
			self.token_expires_at = jwt_expiry_seconds(new_token) * 1000
			return self._request(path, method, _retry=True, **kwargs)
		if self.email and self.password:
			self.login()
			return self._request(path, method, _retry=True, **kwargs)
		raise PlaudTokenExpiredError("Token rejected and no way to refresh (no callback, no credentials)")

	def list_recordings(self):
		data = self._request('/file/simple/web')
		recordings = data.get('data_file_list') or data.get('data') or []
		return [r for r in recordings if not r.get('is_trash')]

	def get_recording_detail(self, file_id, fetch_content=True):
		"""Fetch recording detail as a self-contained archival blob. Returns
		{'detail': <raw response>, 'fetched_content': {data_id: parsed_content}}.

		- detail is the API response verbatim except we strip `embeddings`
		  (opaque vectors we can't use) and the `data_link` URLs inside
		  content_list entries (presigned S3 URLs that expire within hours;
		  their content is resolved into fetched_content below).
		- fetched_content is keyed by data_id. Populated from
		  pre_download_content_list (already inline) and from each content_list
		  entry with task_status == 1 whose content isn't already inline.

		No further decomposition — callers parse the blob at read time.
		"""
		data = self._request(f"/file/detail/{file_id}")
		raw = data.get('data') or data
		raw.pop('embeddings', None)

		fetched = {}
		for item in raw.get('pre_download_content_list') or []:
			data_id = item.get('data_id')
			content = item.get('data_content')
			if not data_id or content is None:
				continue
			# data_content is a string; if it looks like JSON, parse it
			if isinstance(content, str) and content and content[0] in '[{':
				try:
					fetched[data_id] = json.loads(content)
					continue
				except json.JSONDecodeError:
					pass
			fetched[data_id] = content

		for c in raw.get('content_list') or []:
			if c.get('task_status') != 1:
				continue
			data_id = c.get('data_id')
			if not data_id or data_id in fetched:
				continue
			url = c.get('data_link')
			if not url or not fetch_content:
				continue
			try:
				res = requests.get(url, timeout=60)
				res.raise_for_status()
				ctype = res.headers.get('content-type', '')
				if 'json' in ctype:
					fetched[data_id] = res.json()
				else:
					fetched[data_id] = res.text
			except Exception:
				pass

		# Now strip the ephemeral URLs — content is archived in fetched_content
		for c in raw.get('content_list') or []:
			c.pop('data_link', None)

		return {'detail': raw, 'fetched_content': fetched}

	def download_audio(self, file_id, dest_path):
		self._ensure_token()
		url = f"{self.base_url}/file/download/{file_id}"
		headers = {'Authorization': f"Bearer {self.token}"}
		with requests.get(url, headers=headers, stream=True, timeout=120) as res:
			res.raise_for_status()
			with open(dest_path, 'wb') as f:
				for chunk in res.iter_content(chunk_size=8192):
					if chunk:
						f.write(chunk)
