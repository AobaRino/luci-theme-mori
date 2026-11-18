/* Mori: presentation only. No configuration writes or additional RPC. */
(function () {
	'use strict';

	var root = document.documentElement;
	var stored;
	try {
		stored = localStorage.getItem('mori-appearance');
	} catch (_) {}

	var media = window.matchMedia('(prefers-color-scheme: dark)');

	function updateButton(mode) {
		var button = document.querySelector('.mori-theme-toggle');
		if (!button) return;
		var isDark = mode === 'dark';
		button.textContent = isDark ? '☀' : '◐';
		button.setAttribute('aria-label', isDark ? '切换为浅色主题' : '切换为深色主题');
	}

	function applyAppearance(value) {
		var mode = value === 'dark' ? 'dark' : 'light';
		root.setAttribute('data-mori-theme', mode);
		var color = mode === 'dark' ? '#171f1b' : '#27634c';
		var meta = document.querySelector('meta[name="theme-color"]');
		if (meta) meta.setAttribute('content', color);
		updateButton(mode);
	}

	applyAppearance(stored === 'light' || stored === 'dark' ? stored : media.matches ? 'dark' : 'light');
	media.addEventListener('change', function (event) {
		if (!stored) applyAppearance(event.matches ? 'dark' : 'light');
	});

	function element(tag, className, text) {
		var item = document.createElement(tag);
		if (className) item.className = className;
		if (text != null) item.textContent = text;
		return item;
	}

	document.addEventListener('DOMContentLoaded', function () {
		var button = document.querySelector('.mori-theme-toggle');
		if (button) {
			button.addEventListener('click', function () {
				stored = root.getAttribute('data-mori-theme') === 'dark' ? 'light' : 'dark';
				try {
					localStorage.setItem('mori-appearance', stored);
				} catch (_) {}
				applyAppearance(stored);
			});
			updateButton(root.getAttribute('data-mori-theme'));
		}

		var toggle = document.querySelector('a.showSide');
		if (toggle) {
			toggle.addEventListener('click', function (event) {
				event.preventDefault();
			});
			toggle.addEventListener('keydown', function (event) {
				if (event.key === ' ') {
					event.preventDefault();
					toggle.click();
				}
			});
		}

		if (!document.body.classList.contains('mori-native') || document.body.classList.contains('mori-login')) return;
		var page = document.body.getAttribute('data-page') || '';
		var overview = page === '' || page === 'admin' || page === 'admin-status' || page === 'admin-status-overview';
		if (!overview) return;

		document.body.classList.add('mori-overview');
		var container = document.querySelector('#maincontent > .container');
		var view = document.getElementById('view');
		if (!container || !view) return;

		var heading = container.querySelector('h2');
		if (heading) heading.textContent = '网络总览';

		var intro = element('div', 'mori-page-intro');
		intro.appendChild(element('p', '', '设备状态与每一条连接，清晰可见。'));
		var link = element('a', 'mori-overview-link', '查看实时流量 ↗');
		if (window.L && typeof window.L.url === 'function') {
			link.href = window.L.url('admin/status/realtime/bandwidth');
		} else {
			var base = location.pathname.split('/admin/')[0].replace(/\/$/, '');
			if (!/\/cgi-bin\/luci$/.test(base)) base = '/cgi-bin/luci';
			link.href = base + '/admin/status/realtime/bandwidth';
		}
		intro.appendChild(link);
		container.insertBefore(intro, view);

		var grid = element('div', 'mori-summary-grid');
		var fields = [
			{ key: 'cpu', section: 'System', title: 'CPU 使用率', en: 'CPU usage (%)', labels: ['CPU usage (%)', 'CPU 使用率（%）', 'CPU 使用率 (%)'] },
			{ key: 'memory', section: 'Memory', title: '已用内存', en: 'Used', labels: ['Used', '已使用'] },
			{ key: 'users', section: 'Network', title: '在线用户', en: 'Online Users', labels: ['Online Users', '在线用户数', '在线用户'] },
			{ key: 'uptime', section: 'System', title: '运行时间', en: 'Uptime', labels: ['Uptime', '运行时间'] }
		];

		fields.forEach(function (field) {
			var item = element('div', 'mori-stat');
			item.dataset.moriStat = field.key;
			item.appendChild(element('div', 'mori-stat-label', field.title));
			field.value = element('div', 'mori-stat-value', '读取中…');
			field.note = element('div', 'mori-stat-note', '来自系统状态');
			item.appendChild(field.value);
			item.appendChild(field.note);
			grid.appendChild(item);
		});
		container.insertBefore(grid, view);

		function localized(value) {
			return typeof window._ === 'function' ? window._(value) : value;
		}

		var observer;
		function refresh() {
			var sections = Array.from(view.children);
			var sectionMap = {};
			var systemSection;
			var memTitle = localized('Memory');
			var storageTitle = localized('Storage');
			var sysTitle = localized('System');

			sections.forEach(function (section) {
				var h = section.querySelector('h3');
				if (!h) return;
				var title = h.firstChild ? h.firstChild.textContent.trim() : '';
				sectionMap[title] = section;
				if (title === sysTitle) systemSection = section;
				var kind = title === memTitle ? 'memory' : title === storageTitle ? 'storage' : 'wide';
				if (section.dataset.moriSection !== kind) section.dataset.moriSection = kind;
			});

			var rows = Array.from(view.querySelectorAll('tr, .tr')).filter(function (row) {
				return row.children.length >= 2;
			});

			fields.forEach(function (field) {
				var translated = localized(field.en);
				var row = rows.find(function (r) {
					var label = r.firstElementChild.textContent.trim();
					return label === translated || field.labels.indexOf(label) >= 0;
				});
				var value = '尚未获取';
				var note = '来自系统状态';
				var source = sectionMap[localized(field.section)];

				if (source && source.querySelector('[data-indicator="poll-status"][data-style="active"]')) {
					value = '未更新';
					note = '来源区块已隐藏';
				} else if (row) {
					var section = row.closest('.cbi-section');
					if ((section && (section.hidden || section.style.display === 'none')) || row.offsetParent === null) {
						value = '未更新';
						note = '来源区块已隐藏';
					} else {
						var cell = row.children[1];
						var progress = cell.querySelector('.cbi-progressbar');
						if (progress) {
							var raw = progress.getAttribute('title') || '';
							var percent = raw.match(/\(([^)]+)\)/);
							value = percent ? percent[1] : raw || '尚未获取';
							note = raw.replace(/\s*\([^)]+\)$/, '') || '来自系统状态';
						} else {
							value = cell.textContent.trim() || '尚未获取';
						}
						if (field.key === 'uptime') {
							var duration = value.match(/^(\d+)d\s+(\d+)h/);
							if (duration) {
								note = value;
								value = duration[1] + ' 天 ' + duration[2] + ' 小时';
							}
						}
					}
				}
				if (field.value.textContent !== value) field.value.textContent = value;
				if (field.note.textContent !== note) field.note.textContent = note;
			});

			// Move the existing node, retaining LuCI's polling references and controls.
			if (systemSection && view.lastElementChild !== systemSection) {
				view.appendChild(systemSection);
			}
			if (observer) observer.takeRecords();
		}

		var timer = 0;
		observer = new MutationObserver(function () {
			if (timer) return;
			timer = setTimeout(function () {
				timer = 0;
				requestAnimationFrame(refresh);
			}, 60);
		});
		observer.observe(view, {
			childList: true,
			subtree: true,
			characterData: true,
			attributes: true,
			attributeFilter: ['style', 'title', 'data-style']
		});
		refresh();
	});
})();
