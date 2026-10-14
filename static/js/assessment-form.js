(() => {
  const form = document.querySelector('#assessment-form');
  const configNode = document.querySelector('#barthel-preview-config');
  if (!form || !configNode) return;
  const config = JSON.parse(configNode.textContent);
  const score = document.querySelector('#barthel-score');
  const dependency = document.querySelector('#barthel-dependency');
  const careNeed = document.querySelector('#barthel-care-need');
  const progress = document.querySelector('#barthel-progress');
  const update = () => {
    let total = 0;
    let answered = 0;
    const values = new FormData(form);
    for (const field of config.fields) {
      const value = values.get(field.name);
      if (value !== null && Object.hasOwn(field.scores, value)) {
        total += Number(field.scores[value]);
        answered += 1;
      }
    }
    const complete = answered === config.fields.length;
    progress.textContent = complete ? '' : `${answered}/${config.fields.length}. ${progress.dataset.incomplete}`;
    score.textContent = complete ? `${total}/100` : score.dataset.awaiting;
    const band = complete ? config.bands.find(item => total >= Number(item.lower) && total <= Number(item.upper)) : null;
    dependency.textContent = band?.dependency || '';
    careNeed.textContent = band?.care_need || '';
  };
  form.addEventListener('change', update);
  window.addEventListener('pageshow', update);
  update();
})();
