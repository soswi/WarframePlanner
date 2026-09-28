export class Toast {
  constructor(element) {
    this.element = element;
    this.timer = null;
  }

  show(message, isError = false) {
    this.element.textContent = message;
    this.element.classList.toggle("error", isError);
    this.element.hidden = false;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { this.element.hidden = true; }, isError ? 6000 : 2200);
  }
}
