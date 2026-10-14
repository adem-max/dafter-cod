// Runs inside the block. The choice is a per-user preference saved on the
// server, so it follows the user on every computer and phone.
// Values: "open" (default), "collapsed", "hidden".
const KEY = "dz_cod_home_guide";
const box = root_element.querySelector(".cod-home");
const toggle = root_element.querySelector(".toggle");
// The block's frame on the page, to hide it completely
const block = root_element.host.closest(".ce-block") || root_element.host;

function show(state) {
	box.classList.toggle("collapsed", state === "collapsed");
	toggle.textContent = state === "collapsed" ? __("Afficher") : __("Réduire");
	block.style.display = state === "hidden" ? "none" : "";
}

function save(state) {
	show(state);
	frappe.defaults.set_user_default_local(KEY, state);
	frappe.xcall("dz_cod.cod.home.set_guide_state", { state });
}

// English guide for users whose language is English (en, en-US, en-GB...)
if ((frappe.boot.lang || "").startsWith("en")) {
	box.classList.add("lang-en");
}

show(frappe.defaults.get_user_default(KEY) || "open");

toggle.addEventListener("click", () => {
	save(box.classList.contains("collapsed") ? "open" : "collapsed");
});

root_element.querySelector(".dismiss").addEventListener("click", () => {
	frappe.confirm(
		__("Masquer ce guide ? Vous pourrez le réafficher depuis Paramètres COD."),
		() => save("hidden")
	);
});
