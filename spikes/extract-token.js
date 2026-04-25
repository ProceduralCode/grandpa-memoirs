/*
 * Paste this into the browser DevTools Console while signed in to web.plaud.ai.
 * It searches localStorage and sessionStorage for JWT-shaped values, copies
 * the first one to the clipboard, and shows where it found it. Console output
 * tells us the storage key so we can later make a tighter one-click bookmarklet.
 */
(function () {
	const isJwt = (s) =>
		typeof s === 'string' &&
		/^eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(s);

	const findIn = (storage, label) => {
		const out = [];
		for (let i = 0; i < storage.length; i++) {
			const key = storage.key(i);
			const val = storage.getItem(key);
			if (isJwt(val)) {
				out.push({ source: label, key, value: val });
				continue;
			}
			if (val && (val.startsWith('{') || val.startsWith('['))) {
				try {
					const obj = JSON.parse(val);
					const walk = (node, path) => {
						if (isJwt(node)) {
							out.push({ source: label, key: path, value: node });
							return;
						}
						if (node && typeof node === 'object') {
							for (const [k, v] of Object.entries(node)) {
								walk(v, `${path}.${k}`);
							}
						}
					};
					walk(obj, key);
				} catch (e) {}
			}
		}
		return out;
	};

	const found = [
		...findIn(localStorage, 'localStorage'),
		...findIn(sessionStorage, 'sessionStorage'),
	];

	if (found.length === 0) {
		console.warn('No JWT found in localStorage/sessionStorage. Token may be in cookies or held in memory only.');
		alert('No JWT found in storage. Check the Network tab fallback.');
		return;
	}

	console.log('JWT candidates found:', found);
	const summary = found
		.map((t) => `${t.source} -> ${t.key}\n  ${t.value.substring(0, 40)}...`)
		.join('\n\n');

	const first = found[0].value;
	if (navigator.clipboard && navigator.clipboard.writeText) {
		navigator.clipboard.writeText(first).then(
			() => alert(`Found ${found.length} JWT(s). First one copied to clipboard.\n\n${summary}`),
			() => prompt('Copy this JWT:', first)
		);
	} else {
		prompt('Copy this JWT:', first);
	}
})();
