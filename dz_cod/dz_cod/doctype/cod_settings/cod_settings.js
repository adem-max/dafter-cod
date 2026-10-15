// Paramètres COD form.

frappe.ui.form.on("COD Settings", {
	refresh(frm) {
		// Brings back the welcome guide on the COD home page for the current
		// user, after they closed it with ✕ (see setup/home_block/home.js).
		frm.add_custom_button(__("Réafficher le guide d'accueil"), () => {
			frappe.xcall("dz_cod.cod.home.set_guide_state", { state: "open" }).then(() => {
				frappe.defaults.set_user_default_local("dz_cod_home_guide", "open");
				frappe.show_alert({ message: __("Le guide est de retour sur la page Accueil COD."), indicator: "green" });
			});
		});
	},
});
