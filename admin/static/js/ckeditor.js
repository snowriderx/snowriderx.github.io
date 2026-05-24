/* ================================================================
   CKEditor 5 Classic Build v41.4.2 — full CMS configuration.

   Key fixes vs previous version:
   1. Base64UploadAdapter moved OUT of extraPlugins config and into
      the .then() callback.  extraPlugins calls plugin functions as
      constructors at registration time — before FileRepository is
      initialised — so editor.plugins.get('FileRepository') threw,
      silently making CKEditor fall back to its default toolbar.
   2. Source / Maximize button text was invisible because
      .ck-button__label is hidden by CKEditor's own CSS on text-only
      buttons.  Custom buttons now use plain CSS instead of ck-* classes.
   ================================================================ */

/** textarea-id → ClassicEditor instance */
var CKEditors = {};

/**
 * Resolve the ClassicEditor constructor from whichever build is loaded:
 *   - Classic build CDN  → global ClassicEditor
 *   - Super-build CDN    → global CKEDITOR.ClassicEditor
 */
function _getClassicEditor() {
  if (typeof ClassicEditor !== 'undefined') return ClassicEditor;
  if (typeof CKEDITOR !== 'undefined' && CKEDITOR.ClassicEditor) return CKEDITOR.ClassicEditor;
  return null;
}

/**
 * Initialise CKEditor 5 on one or more textareas and wire the
 * form-submit sync so textarea values are updated before POST.
 *
 * @param {string[]} ids     Textarea id attributes.
 * @param {string}   formId  id of the containing <form>.
 * @param {object}   [opts]
 *   opts.uploadUrl    — real image upload endpoint (future use)
 *   opts.contentsCss  — site stylesheet URL for WYSIWYG preview
 */
function initCKEditors(ids, formId, opts) {
  opts = opts || {};
  var form = document.getElementById(formId);

  ids.forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;

    var _CKE = _getClassicEditor();
    if (!_CKE) { console.error('CKEditor not loaded for #' + id); return; }

    /* ── Pre-process textarea HTML before CKEditor reads it ──────────
       CKEditor reads the textarea value during create() — before .then()
       fires — so toView patches applied in .then() are too late.
       Instead, rewrite root-relative src → absolute directly in the
       textarea, then toData strips the origin back out on save.
    ──────────────────────────────────────────────────────────────── */
    if (opts.imageBaseUrl) {
      var _preOrigin = opts.imageBaseUrl.replace(/\/$/, '').match(/^(https?:\/\/[^/]+)/);
      _preOrigin = _preOrigin ? _preOrigin[1] : '';
      if (_preOrigin) {
        el.value = el.value.replace(/src="(\/[^"]+)"/g, 'src="' + _preOrigin + '$1"');
      }
    }

    _CKE.create(el, _buildConfig(opts))
      .then(function (editor) {

        /* ── Image upload adapter ─────────────────────────────────
           Set AFTER initialization so FileRepository is available.
           Server mode: POST multipart to uploadUrl, expect {"url":"..."}.
           Base64 fallback when uploadUrl is not provided.
        ──────────────────────────────────────────────────────── */
        if (opts.uploadUrl) {
          editor.plugins.get('FileRepository').createUploadAdapter =
            function (loader) {
              var xhr = null;
              return {
                upload: function () {
                  return loader.file.then(function (file) {
                    return new Promise(function (resolve, reject) {
                      var ts = Math.floor(Date.now() / 1000);
                      var dot = file.name.lastIndexOf('.');
                      var base = dot >= 0 ? file.name.slice(0, dot) : file.name;
                      var ext  = dot >= 0 ? file.name.slice(dot + 1).toLowerCase() : 'jpg';
                      var filename = base + '_' + ts + '.' + ext;
                      var remotePath = opts.uploadSubfolder + '/' + filename;

                      var fd = new FormData();
                      fd.append('file', file, filename);
                      fd.append('path', remotePath);

                      xhr = new XMLHttpRequest();
                      xhr.open('POST', opts.uploadUrl, true);
                      if (opts.uploadApiKey) {
                        xhr.setRequestHeader('X-API-Key', opts.uploadApiKey);
                      }
                      xhr.onload = function () {
                        if (xhr.status !== 200) {
                          reject('Upload failed: ' + xhr.status);
                          return;
                        }
                        var res;
                        try { res = JSON.parse(xhr.responseText); } catch (e) { reject('Bad JSON'); return; }
                        if (!res.ok) { reject((res.error || 'Upload error')); return; }
                        var baseUrl = (opts.imageBaseUrl || '').replace(/\/$/, '');
                        resolve({ default: baseUrl + '/' + remotePath });
                      };
                      xhr.onerror = function () { reject('Network error'); };
                      xhr.send(fd);
                    });
                  });
                },
                abort: function () { if (xhr) xhr.abort(); }
              };
            };
        } else {
          editor.plugins.get('FileRepository').createUploadAdapter =
            function (loader) {
              return {
                upload: function () {
                  return loader.file.then(function (file) {
                    return new Promise(function (resolve, reject) {
                      var reader = new FileReader();
                      reader.onload  = function () { resolve({ default: reader.result }); };
                      reader.onerror = function () { reject(reader.error); };
                      reader.readAsDataURL(file);
                    });
                  });
                },
                abort: function () {}
              };
            };
        }

        /* ── toData: strip origin prefix back out before saving to DB ──
           The textarea was pre-processed to have absolute URLs so the
           editor displays images correctly. On save, convert back to
           root-relative so DB content stays portable.
        ──────────────────────────────────────────────────────────── */
        if (opts.imageBaseUrl) {
          var originMatch = opts.imageBaseUrl.replace(/\/$/, '').match(/^(https?:\/\/[^/]+)/);
          var origin = originMatch ? originMatch[1] : '';
          if (origin) {
            var escapedOrigin = origin.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            var origToData = editor.data.processor.toData.bind(editor.data.processor);
            editor.data.processor.toData = function (frag) {
              return origToData(frag).replace(
                new RegExp('src="' + escapedOrigin + '(\\/[^"]+)"', 'g'),
                'src="$1"'
              );
            };
          }
        }

        /* Save initial HTML for orphan-delete diff on submit */
        if (opts.deleteUrl) {
          editor._initialHtml = editor.getData();
        }

        CKEditors[id] = editor;
        _addSourceToggle(editor);
        _addMaximizeToggle(editor);
      })
      .catch(function (err) {
        console.error('CKEditor 5 init failed for #' + id, err);
      });
  });

  /* Sync every live editor → its textarea before the form POSTs.
     If deleteUrl is provided, also fire-and-forget delete for orphaned images. */
  if (form) {
    form.addEventListener('submit', function () {
      var orphanUrls = [];

      Object.keys(CKEditors).forEach(function (id) {
        var el = document.getElementById(id);
        var ed = CKEditors[id];
        if (!el || !ed) return;

        var newHtml = (ed._sourceMode && ed._sourceArea)
          ? ed._sourceArea.value
          : ed.getData();

        if (opts.deleteUrl && ed._initialHtml !== undefined) {
          _collectOrphans(ed._initialHtml, newHtml, opts.imageBaseUrl, orphanUrls);
        }

        el.value = newHtml;
      });

      if (opts.deleteUrl && orphanUrls.length) {
        var blob = new Blob([JSON.stringify({ urls: orphanUrls })], { type: 'application/json' });
        navigator.sendBeacon(opts.deleteUrl, blob);
      }
    });
  }
}

/* ── Editor configuration ────────────────────────────────────────── */

function _buildConfig(opts) {
  var config = {

    licenseKey: 'GPL',

    /* ── Disable premium / cloud-only plugins bundled in super-build ──
       These require CKEditor Cloud Services credentials (channelId,
       tokenUrl, etc.).  Without them the editor throws on startup.
    ─────────────────────────────────────────────────────────────── */
    removePlugins: [
      /* ── Real-time collaboration (requires CKEditor Cloud token) ── */
      'RealTimeCollaborativeEditing',
      'RealTimeCollaborativeComments',
      'RealTimeCollaborativeTrackChanges',
      'RealTimeCollaborativeRevisionHistory',
      'PresenceList',
      'Comments',
      'TrackChanges',
      'TrackChangesData',
      'RevisionHistory',
      /* ── CKBox (requires CloudServices / CKEditor Cloud account) ── */
      'CKBox',
      'CKBoxUtils',
      'CKBoxImageEdit',
      /* ── Other premium / credential-required plugins ─────────────── */
      'Pagination',
      'WProofreader',
      'SlashCommand',
      'Template',
      'ExportPdf',
      'ExportWord',
      'ImportWord',
      'FormatPainter',
      'TableOfContents',
      'PasteFromOfficeEnhanced',
      /* ── UI-container plugins (require extra DOM elements) ───────── */
      'DocumentOutline',
      /* ── Commercial-license-only plugins ────────────────────────── */
      'CaseChange',
      'MultiLevelList',
      'AIAssistant',
      'AITextAdapter'
    ],

    /* ── Toolbar ─────────────────────────────────────────────────
       shouldNotGroupWhenFull: true  →  required for '-' row break.
       With false (default), CKEditor collapses items into "..."
       and silently ignores the '-' separator.
    ─────────────────────────────────────────────────────────── */
    toolbar: {
      items: [
        /* ── Row 1 ─────────────────────────────────────────────── */
        'undo', 'redo', '|',
        'findAndReplace', '|',
        'heading', '|',
        'bold', 'italic', 'underline', 'strikethrough',
        'subscript', 'superscript', 'removeFormat', '|',
        'fontFamily', 'fontSize', '|',
        'fontColor', 'fontBackgroundColor', 'highlight',

        '-', /* ── Row 2 ─────────────────────────────────────────── */

        'alignment', '|',
        'bulletedList', 'numberedList', 'todoList', '|',
        'outdent', 'indent', '|',
        'blockQuote', 'code', 'codeBlock', '|',
        'link', 'imageUpload', 'mediaEmbed', '|',
        'insertTable', '|',
        'horizontalLine', 'pageBreak', 'specialCharacters', '|',
        'htmlEmbed'
        /* Source + Maximize appended after create() */
      ],
      shouldNotGroupWhenFull: true
    },

    /* ── Font family ──────────────────────────────────────────── */
    fontFamily: {
      options: [
        'default',
        'Arial, Helvetica, sans-serif',
        'Comic Sans MS, cursive, sans-serif',
        'Courier New, Courier, monospace',
        'Georgia, serif',
        'Lucida Sans Unicode, Lucida Grande, sans-serif',
        'Tahoma, Geneva, sans-serif',
        'Times New Roman, Times, serif',
        'Trebuchet MS, Helvetica, sans-serif',
        'Verdana, Geneva, sans-serif'
      ],
      supportAllValues: true
    },

    /* ── Font size ────────────────────────────────────────────── */
    fontSize: {
      options: [8, 9, 10, 11, 12, 14, 'default', 18, 20, 22, 24, 26, 28, 36, 48, 72],
      supportAllValues: true
    },

    /* ── Heading ──────────────────────────────────────────────── */
    heading: {
      options: [
        { model: 'paragraph', title: 'Paragraph', class: 'ck-heading_paragraph' },
        { model: 'heading1',  view: 'h1', title: 'Heading 1', class: 'ck-heading_heading1' },
        { model: 'heading2',  view: 'h2', title: 'Heading 2', class: 'ck-heading_heading2' },
        { model: 'heading3',  view: 'h3', title: 'Heading 3', class: 'ck-heading_heading3' },
        { model: 'heading4',  view: 'h4', title: 'Heading 4', class: 'ck-heading_heading4' },
        { model: 'heading5',  view: 'h5', title: 'Heading 5', class: 'ck-heading_heading5' },
        { model: 'heading6',  view: 'h6', title: 'Heading 6', class: 'ck-heading_heading6' }
      ]
    },

    /* ── Code block languages ─────────────────────────────────── */
    codeBlock: {
      languages: [
        { language: 'plaintext',  label: 'Plain text'  },
        { language: 'html',       label: 'HTML'        },
        { language: 'css',        label: 'CSS'         },
        { language: 'javascript', label: 'JavaScript'  },
        { language: 'python',     label: 'Python'      },
        { language: 'sql',        label: 'SQL'         }
      ]
    },

    /* ── Image toolbar ────────────────────────────────────────── */
    image: {
      toolbar: [
        'imageStyle:inline', 'imageStyle:block', 'imageStyle:side', '|',
        'toggleImageCaption', 'imageTextAlternative', '|',
        'resizeImage'
      ],
      insert: { type: 'auto' }
    },

    /* ── Table toolbar ────────────────────────────────────────── */
    table: {
      contentToolbar: [
        'tableColumn', 'tableRow', 'mergeTableCells', '|',
        'tableProperties', 'tableCellProperties'
      ]
    },

    /* ── Link ─────────────────────────────────────────────────── */
    link: {
      decorators: {
        openInNewTab: {
          mode:  'manual',
          label: 'Open in new tab',
          attributes: { target: '_blank', rel: 'noopener noreferrer' }
        }
      }
    },

    /* ── List properties ──────────────────────────────────────── */
    list: {
      properties: { styles: true, startIndex: true, reversed: true }
    },

    /* ── GeneralHtmlSupport ───────────────────────────────────────
       Allow all HTML tags/attributes/classes/styles to pass through
       without being stripped or sanitised.  Essential for a CMS
       where editors paste arbitrary HTML.
    ─────────────────────────────────────────────────────────── */
    htmlSupport: {
      allow: [{ name: /.*/, attributes: true, classes: true, styles: true }]
    }
  };

  /* WYSIWYG preview CSS — match live site typography */
  if (opts.contentsCss) {
    config.contentsCss = [opts.contentsCss];
  }

  /* Server upload URL when provided */
  if (opts.uploadUrl) {
    config.simpleUpload = { uploadUrl: opts.uploadUrl };
  }

  return config;
}


/* ================================================================
   Custom Source toggle
   CKEditor 5 Classic Build CDN does not bundle SourceEditing.
   We replicate it with getData() / setData() + a hidden textarea.
   ================================================================ */

function _addSourceToggle(editor) {
  var editorEl   = editor.ui.view.element;
  var editableEl = editor.ui.view.editable.element;

  setTimeout(function () {
    var toolbarItems = editorEl.querySelector('.ck-toolbar__items');
    if (!toolbarItems) return;

    /* Raw HTML textarea */
    var sourceArea = document.createElement('textarea');
    sourceArea.style.cssText = [
      'width:100%', 'min-height:240px', 'display:none',
      'font-family:monospace', 'font-size:12px', 'line-height:1.6',
      'padding:10px', 'box-sizing:border-box', 'resize:vertical',
      'border:1px solid #c4c4c4', 'border-top:none',
      'background:#fff', 'tab-size:2', 'outline:none'
    ].join(';');
    editorEl.appendChild(sourceArea);

    editor._sourceArea = sourceArea;
    editor._sourceMode = false;

    /* Separator */
    var sep = document.createElement('span');
    sep.className = 'ck ck-toolbar__separator';
    toolbarItems.appendChild(sep);

    /* Button — plain CSS, no ck-button__label (that class is hidden by CKEditor CSS) */
    var btn = document.createElement('button');
    btn.type  = 'button';
    btn.title = 'Source';
    btn.textContent = 'Source';
    _applyBtnStyle(btn, false);

    btn.addEventListener('mouseenter', function () {
      if (!editor._sourceMode) _applyBtnStyle(btn, false, true);
    });
    btn.addEventListener('mouseleave', function () {
      _applyBtnStyle(btn, editor._sourceMode);
    });

    btn.addEventListener('click', function () {
      if (!editor._sourceMode) {
        sourceArea.value        = editor.getData();
        editableEl.style.display = 'none';
        sourceArea.style.display = 'block';
        editor._sourceMode      = true;
        _applyBtnStyle(btn, true);
      } else {
        editor.setData(sourceArea.value);
        sourceArea.style.display  = 'none';
        editableEl.style.display  = '';
        editor._sourceMode        = false;
        _applyBtnStyle(btn, false);
      }
    });

    toolbarItems.appendChild(btn);
  }, 0);
}


/* ================================================================
   Custom Maximize toggle — expands editor to fill the viewport.
   ================================================================ */

function _addMaximizeToggle(editor) {
  var editorEl = editor.ui.view.element;

  setTimeout(function () {
    var toolbarItems = editorEl.querySelector('.ck-toolbar__items');
    if (!toolbarItems) return;

    var isMax = false;

    var sep = document.createElement('span');
    sep.className = 'ck ck-toolbar__separator';
    toolbarItems.appendChild(sep);

    var btn = document.createElement('button');
    btn.type  = 'button';
    btn.title = 'Maximize';
    btn.textContent = '⛶';
    btn.style.fontSize = '14px';
    _applyBtnStyle(btn, false);

    btn.addEventListener('mouseenter', function () {
      if (!isMax) _applyBtnStyle(btn, false, true);
    });
    btn.addEventListener('mouseleave', function () {
      _applyBtnStyle(btn, isMax);
    });

    btn.addEventListener('click', function () {
      if (!isMax) {
        editorEl.style.cssText +=
          ';position:fixed!important;inset:0!important;' +
          'width:100%!important;height:100%!important;' +
          'z-index:9999!important;background:#fff!important;margin:0!important';
        editor.ui.view.editable.element.style.height = 'calc(100vh - 100px)';
        document.body.style.overflow = 'hidden';
        isMax = true;
        btn.title = 'Restore';
        _applyBtnStyle(btn, true);
      } else {
        editorEl.removeAttribute('style');
        editor.ui.view.editable.element.style.height = '';
        document.body.style.overflow = '';
        isMax = false;
        btn.title = 'Maximize';
        _applyBtnStyle(btn, false);
      }
    });

    toolbarItems.appendChild(btn);
  }, 0);
}


/* ── Orphan image detection ──────────────────────────────────────── *
   Extracts src values that appear in oldHtml but not in newHtml.
   After toView runs, all src values are absolute (https://origin/...).
   We only track URLs belonging to the client site origin so base64
   data: URLs and external embeds are never sent to ck-delete.
 ─────────────────────────────────────────────────────────────────── */
function _collectOrphans(oldHtml, newHtml, imageBaseUrl, out) {
  var baseUrl = (imageBaseUrl || '').replace(/\/$/, '');
  var originMatch = baseUrl.match(/^(https?:\/\/[^/]+)/);
  var origin = originMatch ? originMatch[1] : baseUrl;

  function extractUrls(html) {
    var urls = {};
    var re = /src="([^"]+)"/g;
    var m;
    while ((m = re.exec(html)) !== null) {
      var u = m[1];
      if (origin && u.indexOf(origin + '/') === 0) {
        urls[u] = true;
      }
    }
    return urls;
  }

  var before = extractUrls(oldHtml);
  var after  = extractUrls(newHtml);
  Object.keys(before).forEach(function (u) {
    if (!after[u]) out.push(u);
  });
}

/* ── Shared button style helper ──────────────────────────────────── *
   We avoid .ck-button__label because CKEditor's CSS sets
   display:none on it for text-only buttons in some toolbar layouts.
   Using plain CSS on the <button> itself guarantees visibility.
 ─────────────────────────────────────────────────────────────────── */
function _applyBtnStyle(btn, active, hover) {
  btn.style.cssText = [
    'border: 1px solid ' + (active ? '#bbb' : 'transparent'),
    'border-radius: 2px',
    'background: ' + (active ? '#e0e0e0' : hover ? 'rgba(0,0,0,.07)' : 'transparent'),
    'cursor: pointer',
    'padding: 4px 8px',
    'font-size: ' + (btn.style.fontSize || '11px'),
    'font-weight: 700',
    'color: #333',
    'letter-spacing: .04em',
    'line-height: 1.5',
    'margin: 0 1px',
    'vertical-align: middle',
    'white-space: nowrap'
  ].join(';');
}
