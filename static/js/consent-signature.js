(() => {
  const form = document.querySelector('#consent-sign-form, #assessment-sign-form, #plan-sign-form');
  const canvas = document.querySelector('#signature-pad');
  if (!form || !canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const data = form.querySelector('[name="signature_data"]');
  const confirmed = form.querySelector('[name="reviewed"]');
  const save = document.querySelector('#signature-save');
  const status = document.querySelector('#signature-status');
  const paper = form.querySelector('[name="paper_signature"]');
  let activePointer = null;
  let drawn = false;
  const hasSignature = () => drawn || Boolean(paper?.files.length);
  const update = () => { save.disabled = !hasSignature() || !confirmed.checked || activePointer !== null; };
  const clear = () => {
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    drawn = false;
    activePointer = null;
    data.value = '';
    confirmed.checked = false;
    status.textContent = status.dataset.empty;
    update();
  };
  const point = (event) => {
    const rect = canvas.getBoundingClientRect();
    return [(event.clientX - rect.left) * canvas.width / rect.width,
            (event.clientY - rect.top) * canvas.height / rect.height];
  };
  canvas.addEventListener('pointerdown', (event) => {
    if (activePointer !== null || (event.pointerType === 'mouse' && event.button !== 0)) return;
    event.preventDefault();
    activePointer = event.pointerId;
    if (paper) paper.value = '';
    canvas.setPointerCapture(event.pointerId);
    ctx.strokeStyle = '#151515';
    ctx.lineWidth = 4;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(...point(event));
    confirmed.checked = false;
    data.value = '';
    update();
  });
  canvas.addEventListener('pointermove', (event) => {
    if (activePointer !== event.pointerId) return;
    event.preventDefault();
    ctx.lineTo(...point(event));
    ctx.stroke();
    drawn = true;
    status.textContent = status.dataset.drawn;
  });
  const finish = (event) => {
    if (activePointer !== event.pointerId) return;
    activePointer = null;
    update();
  };
  canvas.addEventListener('pointerup', finish);
  canvas.addEventListener('pointercancel', finish);
  canvas.addEventListener('lostpointercapture', finish);
  document.querySelector('#signature-clear').addEventListener('click', clear);
  document.querySelector('#signature-redraw').addEventListener('click', clear);
  confirmed.addEventListener('change', update);
  paper?.addEventListener('change', clear);
  form.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && event.target.matches('input:not([type=checkbox])')) {
      event.preventDefault();
    }
  });
  form.addEventListener('submit', (event) => {
    if (!hasSignature() || !confirmed.checked || activePointer !== null || event.submitter !== save) {
      event.preventDefault();
      return;
    }
    data.value = drawn ? canvas.toDataURL('image/png') : '';
    save.disabled = true;
  });
  window.addEventListener('pageshow', clear);
  clear();
})();
