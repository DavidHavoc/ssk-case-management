(() => {
  const form = document.querySelector('#intervention-plan-form');
  if (!form) return;
  const enrollment = form.querySelector('[name=enrollment]');
  const date = form.querySelector('[name=plan_start_date]');
  const kind = form.querySelector('[name=plan_kind]');
  const summary = document.querySelector('#plan-barthel-summary');
  const error = document.querySelector('#plan-preview-error');
  let pending;
  const replaceOptions = (name, rows) => {
    const field = form.querySelector(`[name=${name}]`);
    const selected = field.value;
    field.replaceChildren(new Option('---------', ''), ...rows.map(row => new Option(row.label, row.id)));
    if (rows.some(row => row.id === selected)) field.value = selected;
  };
  const refresh = async () => {
    pending?.abort();
    const controller = new AbortController();
    pending = controller;
    summary.querySelector('[data-barthel-result]').hidden = true;
    summary.querySelector('[data-barthel-empty]').hidden = false;
    error.hidden = true;
    if (!enrollment.value) {
      replaceOptions('specialist', []);
      replaceOptions('previous_plan', []);
      return;
    }
    const url = new URL(form.dataset.previewUrl, window.location.origin);
    url.searchParams.set('enrollment', enrollment.value);
    url.searchParams.set('date', date.value);
    url.searchParams.set('kind', kind.value);
    summary.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url, {signal: controller.signal, headers: {'Accept': 'application/json'}});
      if (!response.ok) throw new Error('preview');
      const data = await response.json();
      if (controller.signal.aborted) return;
      replaceOptions('specialist', data.specialists);
      replaceOptions('previous_plan', data.previous_plans.filter(row => row.id !== form.dataset.planId));
      if (data.barthel) {
        for (const [selector, value] of Object.entries({date: data.barthel.date,
          score: data.barthel.score, dependency: data.barthel.dependency,
          need: data.barthel.care_need, additional: data.barthel.additional_care_needs})) {
          summary.querySelector(`[data-barthel-${selector}]`).textContent = value;
        }
        summary.querySelector('[data-barthel-empty]').hidden = true;
        summary.querySelector('[data-barthel-result]').hidden = false;
        // The server-rendered link belongs to the original selection only.
        summary.querySelector('[data-barthel-link]')?.remove();
      }
    } catch (failure) {
      if (failure.name !== 'AbortError') error.hidden = false;
    } finally {
      if (!controller.signal.aborted) summary.removeAttribute('aria-busy');
    }
  };
  enrollment.addEventListener('change', refresh);
  date.addEventListener('change', refresh);
  kind.addEventListener('change', refresh);
})();
