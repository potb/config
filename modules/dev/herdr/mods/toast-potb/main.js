import { View, div } from "gpui-kit";
import { props, closeOverlay } from "herdr";

export default class Toast extends View {
  init(_props, cx) {
    const id = props()?.overlay;
    cx.timer.after(0, () => closeOverlay(id));
  }

  render() {
    return div();
  }
}
