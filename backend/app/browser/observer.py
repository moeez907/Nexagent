
import asyncio
import logging
from typing import Dict, Any

from playwright.async_api import Page

logger = logging.getLogger("web_agent.browser.observer")


class BrowserObserver:
    """
    Extracts clean, structured, deduplicated DOM snapshots organized by semantic sections.
    Differentiates between search engine result links and destination website listings.
    """

    @staticmethod
    def _closed_page_state(reason: str = "Browser page is closed.") -> Dict[str, Any]:
        return {
            "url": "",
            "title": "",
            "interactive_elements": [],
            "dom_snapshot": f"<dom_structure><body>{reason}</body></dom_structure>",
            "complete_dom_snapshot": f"<html><body>{reason}</body></html>",
            "semantic_dom_snapshot": f"<semantic_dom><body>{reason}</body></semantic_dom>",
            "observation_error": reason,
            "discovered_links": [],
            "popups": [],
            "listing_cards": [],
            "visible_text_summary": reason,
            "scroll_state": {"current_y": 0, "max_y": 0, "is_at_bottom": True},
            "captcha_detected": False,
            "is_closed": True,
        }

    async def observe(self, page: Page) -> Dict[str, Any]:
        if not page:
            return self._closed_page_state("No active browser page.")
        try:
            if page.is_closed():
                return self._closed_page_state()
        except Exception:
            return self._closed_page_state()

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.wait_for_timeout(300)
        except Exception as exc:
            if "target" in str(exc).lower() and "closed" in str(exc).lower():
                return self._closed_page_state("Target page, context or browser has been closed")
            logger.debug("Page did not reach network idle before observation: %s", exc)

        try:
            if page.is_closed():
                return self._closed_page_state()
            url = page.url
            title = await page.title()
        except Exception as exc:
            if "target" in str(exc).lower() and "closed" in str(exc).lower() or getattr(page, "is_closed", lambda: False)():
                return self._closed_page_state("Target page, context or browser has been closed")
            raise

        if url == "about:blank":
            return {
                "url": url,
                "title": title,
                "interactive_elements": [],
                "dom_snapshot": "<dom_structure><body>Blank browser page; navigation is required.</body></dom_structure>",
                "complete_dom_snapshot": "<html><body></body></html>",
                "semantic_dom_snapshot": "<semantic_dom><body>Blank browser page; navigation is required.</body></semantic_dom>",
                "observation_error": None,
                "discovered_links": [],
                "popups": [],
                "listing_cards": [],
                "visible_text_summary": "Blank browser page; navigation is required.",
                "scroll_state": {"current_y": 0, "max_y": 0, "is_at_bottom": True},
                "captcha_detected": False,
            }

        raw_elements = []
        dom_snapshot = ""
        complete_dom_snapshot = ""
        semantic_dom_snapshot = ""
        body_text = ""
        links = []
        popups = []
        scroll_info = {"current_y": 0, "max_y": 0, "is_at_bottom": False}
        captcha_detected = False

        for attempt in range(3):
            try:
                data = await page.evaluate("""() => {
                    const isVisible = (el) => {
                        const style = window.getComputedStyle(el);
                        if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') {
                            return false;
                        }
                        if (style.display === 'contents') {
                            return true;
                        }
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };

                    const getCleanText = (el) => {
                        return (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                    };

                    const getAccessibleName = (el) => {
                        const labelledBy = (el.getAttribute('aria-labelledby') || '')
                            .split(/\\s+/)
                            .filter(Boolean)
                            .map(id => document.getElementById(id))
                            .filter(Boolean)
                            .map(getCleanText)
                            .filter(Boolean)
                            .join(' ');
                        const imgAlt = el.querySelector('img')?.getAttribute('alt') || el.getAttribute('alt') || '';
                        const svgTitle = el.querySelector('svg title')?.textContent || '';
                        const svgAria = el.querySelector('svg')?.getAttribute('aria-label') || '';
                        const iconClass = (typeof el.className === 'string')
                            ? (el.className.split(/\\s+/).find(c => /(?:search|cart|bag|menu|nav|close|filter|account|login|user)/i.test(c)) || '')
                            : '';
                        return labelledBy
                            || el.getAttribute('aria-label')
                            || (el.labels && el.labels.length ? getCleanText(el.labels[0]) : '')
                            || el.getAttribute('title')
                            || svgTitle
                            || svgAria
                            || el.getAttribute('placeholder')
                            || imgAlt
                            || iconClass
                            || el.getAttribute('name')
                            || el.getAttribute('type')
                            || el.tagName.toLowerCase();
                    };

                    const cleanUrl = (rawHref) => {
                        if (!rawHref || rawHref.startsWith('#') || rawHref.startsWith('javascript:')) return '';
                        try {
                            const u = new URL(rawHref, document.baseURI);
                            return u.href;
                        } catch(e) {
                            return rawHref;
                        }
                    };

                    const compactUrl = (rawHref) => {
                        if (!rawHref) return '';
                        try {
                            const url = new URL(rawHref, document.baseURI);
                            return `${url.origin}${url.pathname}${url.search}`;
                        } catch (e) {
                            return rawHref;
                        }
                    };

                    // Clean up any stale agent refs from previous steps
                    document.querySelectorAll('[data-agent-ref]').forEach(el => el.removeAttribute('data-agent-ref'));

                    const interactive = [];
                    const discoveredLinks = [];
                    const popups = [];
                    const popupNodes = new Map();
                    let globalIndex = 0;

                    const rawPopupCandidates = Array.from(document.querySelectorAll(
                        'dialog, [role="dialog"], [aria-modal="true"], [role="alert"], [role="status"], [aria-live]'
                    )).filter(isVisible);

                    const viewportBlockers = Array.from(document.querySelectorAll(
                        '[class*="backdrop"], [class*="mask"], [class*="overlay"], [id*="backdrop"], [id*="mask"], [id*="overlay"]'
                    )).filter((element) => {
                        const style = window.getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        if (style.display === 'none' || style.visibility === 'hidden' || style.pointerEvents === 'none') return false;
                        if (rect.width <= 0 || rect.height <= 0) return false;
                        const centerX = Math.max(0, Math.min(window.innerWidth - 1, window.innerWidth / 2));
                        const centerY = Math.max(0, Math.min(window.innerHeight - 1, window.innerHeight / 2));
                        const hitElements = document.elementsFromPoint(centerX, centerY);
                        const coversViewport = rect.width >= window.innerWidth * 0.5 && rect.height >= window.innerHeight * 0.5;
                        return coversViewport || hitElements.includes(element);
                    });

                    // Combine candidates and filter out nested sub-popups
                    const allCandidates = [...rawPopupCandidates, ...viewportBlockers];
                    const popupCandidatesUnique = allCandidates.filter((popup, index) => {
                        return allCandidates.indexOf(popup) === index &&
                            !allCandidates.some(other => other !== popup && other.contains(popup));
                    });
                    popupCandidatesUnique.forEach((popup, popupIndex) => {
                        const role = popup.getAttribute('role') || (popup.tagName.toLowerCase() === 'dialog' ? 'dialog' : 'modal');
                        const label = getAccessibleName(popup);
                        const popupSignature = `${popup.className || ''} ${popup.id || ''}`.toLowerCase();
                        const isDynamicBlocker = viewportBlockers.includes(popup);
                        const isTransient = role === 'status'
                            || role === 'alert'
                            || Boolean(popup.getAttribute('aria-live'))
                            || /(?:toast|snackbar|notification|flash|message)/.test(popupSignature);
                        const popupText = getCleanText(popup);
                        const severity = /(?:success|added|complete|done|saved|updated|created|sent)/i.test(popupText)
                            ? 'success'
                            : /(?:error|failed|failure|invalid|unable|declined|rejected)/i.test(popupText)
                                ? 'error'
                                : /(?:warning|warn|attention|expired)/i.test(popupText)
                                    ? 'warning'
                                    : 'info';
                        const popupInfo = {
                            id: `popup-${popupIndex}`,
                            role,
                            label: label === popup.tagName.toLowerCase() ? '' : label,
                            text: popupText,
                            type: isTransient ? 'notification' : 'modal',
                            transient: isTransient,
                            severity,
                            modal: isDynamicBlocker || popup.getAttribute('aria-modal') === 'true' || (popup.tagName.toLowerCase() === 'dialog' && popup.open),
                            blocking: isDynamicBlocker
                                || popup.getAttribute('aria-modal') === 'true'
                                || (popup.tagName.toLowerCase() === 'dialog' && popup.open),
                            dynamic: isDynamicBlocker,
                            dismissible: Boolean(popup.querySelector('button, [role="button"], [aria-label*="close" i], [title*="close" i]')),
                            selector: popup.id ? `#${popup.id}` : `.${String(popup.className || '').split(/\\s+/).filter(Boolean).join('.')}`
                        };
                        popups.push(popupInfo);
                        popupNodes.set(popup, popupInfo);
                    });

                    const popupFor = (el) => {
                        let current = el;
                        while (current && current !== document.documentElement) {
                            if (popupNodes.has(current)) return popupNodes.get(current);
                            current = current.parentElement;
                        }
                        return null;
                    };

                    // Extract generic form controls, interactive links, summary elements, clickable buttons, and dynamic pointer elements
                    const baseInteractiveSelector = 'input, textarea, button, select, label, a, summary, ' +
                        '[role="button"], [role="link"], [role="searchbox"], [role="checkbox"], ' +
                        '[role="radio"], [role="combobox"], [role="option"], [role="tab"], ' +
                        '[role="switch"], [role="textbox"], [role="menuitem"], [role="menuitemcheckbox"], ' +
                        '[role="menuitemradio"], [role="treeitem"], [role="gridcell"], [onclick], ' +
                        '[tabindex]:not([tabindex="-1"]), [contenteditable="true"], [data-action], [data-clickable]';

                    const interactiveNodes = Array.from(document.querySelectorAll(baseInteractiveSelector))
                        .filter(el => {
                            if (!isVisible(el) && !['file', 'radio', 'checkbox'].includes(el.type)) return false;
                            // Skip radio/checkbox inputs that have an associated label — the label is the real clickable element.
                            // Playwright cannot click a hidden radio/checkbox when its label intercepts pointer events.
                            if ((el.type === 'radio' || el.type === 'checkbox') && el.tagName.toLowerCase() === 'input') {
                                const hasLabelFor = el.id && document.querySelector(`label[for="${el.id}"]`);
                                const hasWrappingLabel = el.closest('label');
                                if (hasLabelFor || hasWrappingLabel) return false;
                            }
                            return true;
                        });

                    // Dynamically capture custom clickable elements styled with cursor: pointer
                    const interactiveSet = new Set(interactiveNodes);
                    document.querySelectorAll('div, span, li, p, article, section, td, th, img, svg').forEach((el) => {
                        if (interactiveSet.has(el) || !isVisible(el)) return;
                        const style = window.getComputedStyle(el);
                        if (style.cursor === 'pointer' && !style.pointerEvents.includes('none')) {
                        const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                // Skip if any ancestor is already a known interactive element
                                const interactiveAncestorSelector =
                                    'button, select, a, label, summary, ' +
                                    '[role="button"], [role="link"], [role="option"], [role="tab"], ' +
                                    '[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"], ' +
                                    '[role="treeitem"], [role="gridcell"], [role="checkbox"], [role="radio"], ' +
                                    '[role="switch"], [role="combobox"]';
                                const parentInteractive = el.closest(interactiveAncestorSelector);
                                const ancestorInSet = parentInteractive && interactiveSet.has(parentInteractive);
                                if (!parentInteractive || (!ancestorInSet && parentInteractive === el)) {
                                    interactiveNodes.push(el);
                                    interactiveSet.add(el);
                                }
                            }
                        }
                    });

                    const structuredInputs = [];
                    const structuredActions = [];
                    const structuredLinks = [];

                    interactiveNodes.forEach((el) => {
                        const tag = el.tagName.toLowerCase();
                        const rawHref = el.getAttribute('href') || '';
                        const ariaLabel = el.getAttribute('aria-label') || '';
                        const label = getAccessibleName(el);
                        const cleanInnerText = getCleanText(el);
                        const imgAlt = el.querySelector('img')?.getAttribute('alt') || el.getAttribute('alt') || '';
                        const text = cleanInnerText || label || ariaLabel || el.getAttribute('title') || imgAlt || '';
                        const isHeading = tag === 'h1' || tag === 'h2' || tag === 'h3';
                        if (!text && (isHeading || (tag === 'a' && !rawHref))) return;

                        if (rawHref === '#' || rawHref.startsWith('#') || rawHref.startsWith('javascript:')) {
                            if (tag === 'a' && !text) return;
                        }

                        const href = cleanUrl(rawHref);

                        const id = el.id || '';
                        let name = el.getAttribute('name') || '';
                        let type = el.getAttribute('type') || '';
                        const placeholder = el.getAttribute('placeholder') || '';
                        const rawValue = el.value || '';
                        let value = type === 'password' && rawValue ? '[REDACTED]' : rawValue;
                        let checked = typeof el.checked === 'boolean' ? el.checked : null;
                        let ariaChecked = el.getAttribute('aria-checked');
                        if (tag === 'label') {
                            const forId = el.getAttribute('for');
                            const linkedInput = (forId && document.getElementById(forId)) || el.querySelector('input, [role="radio"], [role="checkbox"]');
                            if (linkedInput) {
                                if (!name) name = linkedInput.getAttribute('name') || '';
                                if (!type) type = linkedInput.getAttribute('type') || linkedInput.getAttribute('role') || '';
                                if (!value) value = linkedInput.value || '';
                                if (typeof linkedInput.checked === 'boolean') checked = linkedInput.checked;
                                if (!ariaChecked && linkedInput.getAttribute('aria-checked')) {
                                    ariaChecked = linkedInput.getAttribute('aria-checked');
                                }
                            }
                        }
                        const ariaSelected = el.getAttribute('aria-selected');
                        const dataState = el.getAttribute('data-state');
                        const options = tag === 'select'
                            ? Array.from(el.options || []).map(option => ({
                                label: getCleanText(option),
                                value: option.value,
                                selected: option.selected,
                                disabled: option.disabled
                            }))
                            : null;
                        const selected = tag === 'select'
                            ? options.filter(option => option.selected).map(option => option.value)
                            : null;
                        const validationMessage = el.validationMessage || '';
                        const ariaRequired = el.getAttribute('aria-required') === 'true';
                        const ariaInvalid = el.getAttribute('aria-invalid') === 'true';
                        const popup = popupFor(el);
                        const fileControl = type === 'file';
                        const uploadControl = fileControl || (
                            !['input', 'textarea', 'select'].includes(tag)
                            && Boolean(el.closest('[role="listitem"], fieldset, [role="group"]')?.querySelector('input[type="file"]'))
                        );
                        const contextCandidates = [];
                        let contextCursor = el.parentElement;
                        while (contextCursor && contextCursor !== document.body) {
                            if (contextCursor.matches('[role="listitem"], fieldset, [role="group"]')) {
                                const relatedControlCount = contextCursor.querySelectorAll(
                                    '[role="radio"], [role="checkbox"], [role="switch"], [role="option"]'
                                ).length;
                                if (relatedControlCount > 1) contextCandidates.push(contextCursor);
                            }
                            contextCursor = contextCursor.parentElement;
                        }
                        const formContextNode = contextCandidates.sort((left, right) => {
                            const leftCount = left.querySelectorAll(
                                '[role="radio"], [role="checkbox"], [role="switch"], [role="option"]'
                            ).length;
                            const rightCount = right.querySelectorAll(
                                '[role="radio"], [role="checkbox"], [role="switch"], [role="option"]'
                            ).length;
                            return leftCount - rightCount;
                        })[0] || el.closest('[role="listitem"], fieldset, [role="group"]');
                        const formContext = formContextNode
                            ? getCleanText(formContextNode)
                            : '';

                        const index = globalIndex++;
                        const ref = `agent-${index}`;
                        el.setAttribute('data-agent-ref', ref);
                        interactive.push({
                            index: index,
                            ref: ref,
                            tag: tag,
                            role: el.getAttribute('role') || tag,
                            text: text,
                            aria_label: ariaLabel,
                            label: label,
                            placeholder: placeholder,
                            name: name,
                            id: id,
                            type: type,
                            href: href,
                            compact_href: compactUrl(href),
                            value: value,
                            checked: checked,
                            aria_checked: ariaChecked === null ? null : ariaChecked === 'true',
                            selected_state: checked === true
                                || ariaChecked === 'true'
                                || ariaSelected === 'true'
                                || dataState === 'checked',
                            options: options,
                            selected: selected,
                            form_context: formContext,
                            required: el.required === true || ariaRequired,
                            aria_required: ariaRequired,
                            invalid: ariaInvalid,
                            expanded: el.getAttribute('aria-expanded') === 'true',
                            controls: el.getAttribute('aria-controls') || '',
                            has_popup: el.getAttribute('aria-haspopup') || '',
                            disabled: el.disabled === true,
                            readonly: el.readOnly === true,
                            validation_message: validationMessage,
                            file_control: fileControl,
                            upload_control: uploadControl,
                            popup: popup
                        });

                        let attrStr = `data-agent-ref="${ref}" index="${index}"`;
                        if (id) attrStr += ` id="${id}"`;
                        if (name) attrStr += ` name="${name}"`;
                        if (type) attrStr += ` type="${type}"`;
                        if (placeholder) attrStr += ` placeholder="${placeholder}"`;
                        if (ariaLabel) attrStr += ` aria-label="${ariaLabel}"`;
                        if (label) attrStr += ` label="${label}"`;
                        if (value) attrStr += ` value="${value}"`;
                        if (options && options.length) {
                            const optionText = options
                                .map(option => `${option.label} [value=${option.value}]`)
                                .join(' | ')
                                .replace(/&/g, '&amp;')
                                .replace(/"/g, '&quot;')
                                .replace(/</g, '&lt;')
                                .replace(/>/g, '&gt;');
                            attrStr += ` options="${optionText}"`;
                        }
                        if (checked !== null) attrStr += ` checked="${checked}"`;
                        if (ariaChecked !== null) attrStr += ` aria-checked="${ariaChecked}"`;
                        if (ariaSelected !== null) attrStr += ` aria-selected="${ariaSelected}"`;
                        if (dataState !== null) attrStr += ` data-state="${dataState}"`;
                        if (el.required) attrStr += ' required="true"';
                        if (ariaRequired) attrStr += ' aria-required="true"';
                        if (ariaInvalid) attrStr += ' aria-invalid="true"';
                        if (el.getAttribute('aria-expanded')) attrStr += ` aria-expanded="${el.getAttribute('aria-expanded')}"`;
                        if (el.getAttribute('aria-controls')) attrStr += ` aria-controls="${el.getAttribute('aria-controls')}"`;
                        if (el.getAttribute('aria-haspopup')) attrStr += ` aria-haspopup="${el.getAttribute('aria-haspopup')}"`;
                        if (el.disabled) attrStr += ' disabled="true"';
                        if (el.readOnly) attrStr += ' readonly="true"';
                        if (validationMessage) attrStr += ` validation="${validationMessage}"`;
                        if (formContext) {
                            const escapedFormContext = formContext
                                .replace(/&/g, '&amp;')
                                .replace(/"/g, '&quot;')
                                .replace(/</g, '&lt;')
                                .replace(/>/g, '&gt;');
                            attrStr += ` form_context="${escapedFormContext}"`;
                        }
                        if (popup) attrStr += ` popup="${popup.id}"`;
                        if (href && !href.startsWith('#')) attrStr += ` href="${href}"`;

                        const displayContent = text || ariaLabel || placeholder || value || '';
                        const nodeXml = `<${tag} ${attrStr}>${displayContent}</${tag}>`;

                        if (tag === 'input' || tag === 'textarea' || tag === 'select') {
                            structuredInputs.push(nodeXml);
                        } else if (tag === 'button' || el.getAttribute('role') === 'button' || type === 'submit') {
                            structuredActions.push(nodeXml);
                        } else {
                            structuredLinks.push(nodeXml);
                        }

                        if (tag === 'a' && href && !href.startsWith('javascript:') && !href.startsWith('#')) {
                            try {
                                const img = el.querySelector('img') || (el.parentElement ? el.parentElement.querySelector('img') : null);
                                let imgSrc = null;
                                if (img) {
                                    imgSrc = img.getAttribute('src') || img.getAttribute('data-src') || img.getAttribute('srcset') || img.currentSrc || img.src;
                                    if (imgSrc && imgSrc.includes(' ')) imgSrc = imgSrc.split(' ')[0];
                                    if (imgSrc && (imgSrc.startsWith('data:') || imgSrc.length < 10)) imgSrc = null;
                                }
                                discoveredLinks.push({
                                    index: index,
                                    ref: ref,
                                    text: text || ariaLabel || href,
                                    url: href,
                                    image: imgSrc || null
                                });
                            } catch (e) {}
                        }
                    });

                    const interactiveByRef = new Map(interactive.map(element => [element.ref, element]));
                    popups.forEach((popup) => {
                        const popupControls = interactive.filter(element =>
                            element.popup && element.popup.id === popup.id && !element.disabled
                        );
                        const closeControls = popupControls
                            .map(element => {
                                const label = [element.text, element.aria_label, element.label, element.title]
                                    .filter(Boolean)
                                    .join(' ')
                                    .replace(/\\s+/g, ' ')
                                    .trim();
                                const normalized = label.toLowerCase();
                                const isClose = /^(close|dismiss|cancel|no thanks|not now|got it|x|×|✕|✖)$/i.test(label)
                                    || /\b(close|dismiss|cancel|no thanks|not now|got it)\b/i.test(label);
                                const isProgressAction = /\b(submit|save|continue|confirm|accept|allow|login|sign in|next|checkout|buy|send)\b/i.test(normalized);
                                return isClose && !isProgressAction ? {
                                    ref: element.ref,
                                    index: element.index,
                                    label,
                                    confidence: /\b(close|dismiss|cancel)\b/i.test(label) ? 'high' : 'medium'
                                } : null;
                            })
                            .filter(Boolean);
                        popup.popup_controls = popupControls.map(element => ({
                            ref: element.ref,
                            index: element.index,
                            tag: element.tag,
                            role: element.role,
                            label: element.label || element.aria_label || element.text || ''
                        }));
                        popup.close_refs = [...new Set(closeControls.map(control => control.ref))];
                        popup.close_controls = closeControls;
                        popup.dismissible = popup.close_refs.length > 0;
                    });

                    // 4. Assemble Clean Structured DOM Tree
                    let finalSnapshot = '<dom_structure>\\n';

                    if (structuredInputs.length > 0) {
                        finalSnapshot += '  <search_and_form_controls>\\n';
                        structuredInputs.forEach(inp => finalSnapshot += `    ${inp}\\n`);
                        finalSnapshot += '  </search_and_form_controls>\\n\\n';
                    }

                    if (structuredActions.length > 0) {
                        finalSnapshot += '  <action_buttons>\\n';
                        structuredActions.forEach(btn => finalSnapshot += `    ${btn}\\n`);
                        finalSnapshot += '  </action_buttons>\\n\\n';
                    }

                    if (structuredLinks.length > 0) {
                        finalSnapshot += '  <content_and_navigation_links>\\n';
                        structuredLinks.forEach(link => finalSnapshot += `    ${link}\\n`);
                        finalSnapshot += '  </content_and_navigation_links>\\n';
                    }

                    finalSnapshot += '</dom_structure>';

                    const escapeXml = (value) => String(value || '')
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/"/g, '&quot;');

                    const buildCompleteNode = (node) => {
                        if (node.nodeType === Node.TEXT_NODE) {
                            const text = node.textContent.replace(/\\s+/g, ' ').trim();
                            return text ? escapeXml(text) : '';
                        }
                        if (node.nodeType !== Node.ELEMENT_NODE) return '';

                        const attributes = Array.from(node.attributes)
                            .map(attribute => `${attribute.name}="${escapeXml(attribute.value)}"`)
                            .join(' ');
                        const tag = node.tagName.toLowerCase();
                        const opening = attributes ? `<${tag} ${attributes}>` : `<${tag}>`;
                        const children = Array.from(node.childNodes)
                            .map(child => buildCompleteNode(child))
                            .filter(Boolean)
                            .join('');
                        return `${opening}${children}</${tag}>`;
                    };

                    const semanticInteractiveByRef = new Map(
                        interactive.map(element => [element.ref, element])
                    );
                    const semanticTags = new Set([
                        'html', 'body', 'header', 'footer', 'main', 'nav', 'aside',
                        'section', 'article', 'form', 'fieldset', 'legend', 'label',
                        'dialog', 'details', 'summary', 'table', 'caption', 'thead',
                        'tbody', 'tfoot', 'tr', 'th', 'td', 'ul', 'ol', 'li',
                        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'address',
                        'blockquote', 'pre', 'figure', 'figcaption', 'time',
                        'button', 'a', 'input', 'select', 'textarea', 'img'
                    ]);
                    const semanticRoles = new Set([
                        'banner', 'complementary', 'contentinfo', 'dialog', 'document',
                        'feed', 'form', 'grid', 'gridcell', 'group', 'list', 'listbox',
                        'listitem', 'main', 'navigation', 'option', 'region', 'row',
                        'rowgroup', 'search', 'status', 'tablist', 'tabpanel', 'tree',
                        'treeitem'
                    ]);
                    const semanticInteractiveRoles = new Set([
                        'button', 'checkbox', 'combobox', 'link', 'menuitem',
                        'menuitemcheckbox', 'menuitemradio', 'option', 'radio',
                        'searchbox', 'slider', 'spinbutton', 'switch', 'tab',
                        'textbox', 'treeitem', 'gridcell'
                    ]);
                    const semanticEscapedText = (value) => escapeXml(String(value || '').replace(/\\s+/g, ' ').trim());
                    const directText = (node) => Array.from(node.childNodes)
                        .filter(child => child.nodeType === Node.TEXT_NODE)
                        .map(child => child.textContent.replace(/\\s+/g, ' ').trim())
                        .filter(Boolean)
                        .join(' ');
                    const semanticAttributes = (node, role, ref) => {
                        const element = ref ? semanticInteractiveByRef.get(ref) : null;
                        const attributes = [];
                        if (ref) attributes.push(`ref="${escapeXml(ref)}"`);
                        if (element && element.index !== undefined) attributes.push(`index="${element.index}"`);
                        if (role && (!element || role !== element.tag)) attributes.push(`role="${escapeXml(role)}"`);
                        if (element) {
                            for (const key of ['label', 'aria_label', 'placeholder', 'name', 'id', 'type', 'href', 'value']) {
                                const attributeValue = key === 'href' ? (element.compact_href || element[key]) : element[key];
                                if (attributeValue && !(key === 'label' && attributeValue === element.tag) && !(key === 'type' && attributeValue === element.tag)) {
                                    attributes.push(`${key}="${escapeXml(attributeValue)}"`);
                                }
                            }
                            const isChecked = element.checked === true || element.aria_checked === true || element.selected_state === true;
                            if (isChecked) {
                                attributes.push('checked="true"');
                            } else if (element.checked === false || element.aria_checked === false) {
                                attributes.push('checked="false"');
                            }
                            if (element.selected && element.selected.length) attributes.push(`selected="${escapeXml(element.selected.join(','))}"`);
                            if (element.options && element.options.length) {
                                const options = element.options.map(option =>
                                    `${option.label} [value=${option.value}]${option.selected ? ' [selected]' : ''}${option.disabled ? ' [disabled]' : ''}`
                                ).join(' | ');
                                attributes.push(`options="${escapeXml(options)}"`);
                            }
                            if (element.required) attributes.push('required="true"');
                            if (element.aria_required) attributes.push('aria_required="true"');
                            if (element.invalid) attributes.push('invalid="true"');
                            if (element.popup) attributes.push(`popup="${escapeXml(element.popup.id)}"`);
                            if (element.disabled) attributes.push('disabled="true"');
                            if (element.readonly) attributes.push('readonly="true"');
                            if (element.validation_message) attributes.push(`validation="${escapeXml(element.validation_message)}"`);
                        } else if (node.getAttribute('aria-label')) {
                            attributes.push(`aria_label="${escapeXml(node.getAttribute('aria-label'))}"`);
                        }
                        return attributes.join(' ');
                    };
                    const buildSemanticNode = (node) => {
                        if (node.nodeType === Node.TEXT_NODE) {
                            return semanticEscapedText(node.textContent);
                        }
                        if (node.nodeType !== Node.ELEMENT_NODE) return '';

                        const tag = node.tagName.toLowerCase();
                        if (['script', 'style', 'template', 'noscript', 'head'].includes(tag)) return '';

                        const style = window.getComputedStyle(node);
                        if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') {
                            return '';
                        }

                        if (tag === 'img') {
                            const src = node.getAttribute('src') || node.getAttribute('data-src') || node.getAttribute('srcset') || node.currentSrc || node.src;
                            const cleanSrc = src && !src.startsWith('data:') && src.length > 10 ? escapeXml(src.split(' ')[0]) : '';
                            const alt = escapeXml(node.getAttribute('alt') || '');
                            if (cleanSrc) {
                                return `<img src="${cleanSrc}"${alt ? ` alt="${alt}"` : ''} />`;
                            }
                            return '';
                        }

                        const ref = node.getAttribute('data-agent-ref') || '';
                        const role = node.getAttribute('role') || (semanticInteractiveByRef.get(ref) || {}).role || '';
                        const isInteractive = Boolean(ref) || Boolean(role && semanticInteractiveRoles.has(role));
                        const hasSemanticTag = semanticTags.has(tag);

                        // Only prune leaf elements if zero dimensions and not interactive
                        const isLeaf = !node.childNodes || node.childNodes.length === 0;
                        if (isLeaf && !isInteractive) {
                            const rect = node.getBoundingClientRect();
                            if (rect.width <= 0 && rect.height <= 0) return '';
                        }

                        const childMarkup = Array.from(node.childNodes)
                            .map(child => buildSemanticNode(child))
                            .filter(Boolean)
                            .join(' ');

                        const ownText = directText(node);
                        const text = !childMarkup && !isInteractive ? getCleanText(node) : '';
                        const hasContent = Boolean(childMarkup || text);
                        const meaningful = isInteractive || (hasContent && (hasSemanticTag || Boolean(role && semanticRoles.has(role))));
                        if (!meaningful) return childMarkup;

                        const outputTag = hasSemanticTag || isInteractive || role ? tag : 'text';
                        const attributes = semanticAttributes(node, outputTag === 'text' ? '' : role, ref);
                        const opening = attributes ? `<${outputTag} ${attributes}>` : `<${outputTag}>`;
                        const escapedText = text ? semanticEscapedText(text) : '';
                        const content = childMarkup === escapedText
                            ? childMarkup
                            : [escapedText, childMarkup].filter(Boolean).join(' ');
                        return `${opening}${content}</${outputTag}>`;
                    };

                    const bodyText = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').trim();

                    const completeDomSnapshot = document.documentElement
                        ? buildCompleteNode(document.documentElement)
                        : '';
                    const semanticBody = document.body ? buildSemanticNode(document.body) : '';
                    const semanticDomSnapshot = semanticBody
                        ? `<semantic_dom>\n${semanticBody}\n</semantic_dom>`
                        : '';

                    const isVisibleChallengeIframe = Array.from(document.querySelectorAll('iframe')).some(f => {
                        if (!f.src) return false;
                        const isChallenge = f.src.includes('recaptcha') || f.src.includes('hcaptcha') || f.src.includes('turnstile');
                        if (!isChallenge) return false;
                        const rect = f.getBoundingClientRect();
                        return rect.width > 120 && rect.height > 40;
                    });

                    // Extract visible product / listing cards with actual web images and prices
                    const extractedListingCards = [];
                    try {
                        const pricePattern = /(?:(?:rs\\.?|pkr|\\$|£|€|inr)\\s*[\\d,]+(?:\\.\\d+)?|[\\d,]+(?:\\.\\d+)?\\s*(?:rs|pkr))/i;
                        const cardSelectors = [
                            '[data-qa-locator="product-item"]',
                            '[data-tracking="product-card"]',
                            '[data-asin]',
                            '[data-item-id]',
                            '.gridItem--Yd0sa',
                            '.s-result-item',
                            'div[class*="productCard" i]',
                            'div[class*="product-card" i]',
                            'div[class*="product_card" i]',
                            'div[class*="item-card" i]',
                            'div[class*="search-result" i]',
                            'li[class*="product" i]'
                        ];
                        const seenTitles = new Set();
                        document.querySelectorAll(cardSelectors.join(', ')).forEach((cardEl) => {
                            if (!isVisible(cardEl) || extractedListingCards.length >= 20) return;
                            const cardText = (cardEl.innerText || '').replace(/\\s+/g, ' ').trim();
                            if (!pricePattern.test(cardText)) return;

                            const titleEl = cardEl.querySelector('a[title], [class*="title" i], [class*="name" i], h2, h3, h4, a');
                            const title = (titleEl ? (titleEl.getAttribute('title') || titleEl.innerText) : '').replace(/\\s+/g, ' ').trim();
                            if (!title || title.length < 4 || seenTitles.has(title)) return;
                            seenTitles.add(title);

                            const priceMatch = cardText.match(pricePattern);
                            const price = priceMatch ? priceMatch[0].trim() : '';

                            const linkEl = cardEl.tagName.toLowerCase() === 'a' ? cardEl : cardEl.querySelector('a[href]');
                            const url = linkEl ? linkEl.href : '';

                            const imgEl = cardEl.querySelector('img');
                            let imgSrc = null;
                            if (imgEl) {
                                imgSrc = imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || imgEl.getAttribute('srcset') || imgEl.currentSrc || imgEl.src;
                                if (imgSrc && imgSrc.includes(' ')) imgSrc = imgSrc.split(' ')[0];
                                if (imgSrc && (imgSrc.startsWith('data:') || imgSrc.length < 10)) imgSrc = null;
                            }

                            extractedListingCards.push({
                                title: title,
                                price: price,
                                image: imgSrc || null,
                                url: url,
                                details: cardText.slice(0, 160)
                            });
                        });
                    } catch (e) {}

                    return {
                        interactive: interactive,
                        dom_snapshot: finalSnapshot,
                        complete_dom_snapshot: completeDomSnapshot,
                        semantic_dom_snapshot: semanticDomSnapshot,
                        links: discoveredLinks,
                        listing_cards: extractedListingCards,
                        popups: popups,
                        body_text: bodyText,
                        scroll: {
                            current_y: window.scrollY,
                            max_y: document.documentElement.scrollHeight - window.innerHeight,
                            is_at_bottom: window.scrollY >= (document.documentElement.scrollHeight - window.innerHeight - 10)
                        },
                        captcha_heuristic: isVisibleChallengeIframe
                    };
                }""")

                raw_elements = data.get("interactive", [])
                dom_snapshot = data.get("dom_snapshot", "")
                complete_dom_snapshot = data.get("complete_dom_snapshot", "")
                semantic_dom_snapshot = data.get("semantic_dom_snapshot", "")
                links = data.get("links", [])
                popups = data.get("popups", [])
                body_text = data.get("body_text", "")
                scroll_info = data.get("scroll", scroll_info)
                captcha_detected = data.get("captcha_heuristic", False)
                listing_cards = data.get("listing_cards", [])
                break

            except Exception as e:
                err_msg = str(e).lower()
                if "target" in err_msg and "closed" in err_msg:
                    logger.info("Target page, context or browser was closed during DOM extraction.")
                    return self._closed_page_state("Target page, context or browser has been closed")
                if ("execution context was destroyed" in err_msg or "navigating" in err_msg) and attempt < 2:
                    logger.warning(f"Observer attempt {attempt + 1}: Context destroyed. Waiting for DOM load...")
                    await asyncio.sleep(0.5)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except Exception:
                        pass
                else:
                    logger.error(f"Observer extraction failed: {e}")
                    break

        if not isinstance(complete_dom_snapshot, str) or not complete_dom_snapshot:
            logger.error("Raw complete DOM generation failed during observation.")
        if not isinstance(semantic_dom_snapshot, str) or not semantic_dom_snapshot.strip():
            logger.error("Semantic DOM generation failed after observer retries.")

        return {
            "url": url,
            "title": title,
            "interactive_elements": raw_elements,
            "dom_snapshot": dom_snapshot,
            "complete_dom_snapshot": complete_dom_snapshot or dom_snapshot,
            "semantic_dom_snapshot": semantic_dom_snapshot,
            "observation_error": (
                "Semantic DOM generation failed after observer retries."
                if not isinstance(semantic_dom_snapshot, str) or not semantic_dom_snapshot.strip()
                else None
            ),
            "discovered_links": links,
            "popups": popups,
            "listing_cards": listing_cards if 'listing_cards' in locals() else [],
            "visible_text_summary": body_text,
            "scroll_state": scroll_info,
            "captcha_detected": captcha_detected
        }


observer = BrowserObserver()
