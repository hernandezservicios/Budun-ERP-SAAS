/*
  JavaScript ligero del Design System (FASE 5). Sin frameworks ni build
  step: progressive enhancement basado en atributos `data-*`. Cada
  componente se auto-inicializa en DOMContentLoaded.
*/
(function () {
    "use strict";

    /* --- Sidebar (colapsable en tablet/móvil) ------------------------ */
    function initSidebar() {
        var shell = document.querySelector(".shell");
        var toggle = document.querySelector("[data-sidebar-toggle]");
        var backdrop = document.querySelector("[data-sidebar-backdrop]");
        if (!shell || !toggle) return;

        function cerrar() {
            shell.classList.remove("sidebar-abierto");
            toggle.setAttribute("aria-expanded", "false");
        }

        function alternar() {
            var abierto = shell.classList.toggle("sidebar-abierto");
            toggle.setAttribute("aria-expanded", abierto ? "true" : "false");
        }

        toggle.addEventListener("click", alternar);
        if (backdrop) backdrop.addEventListener("click", cerrar);
        document.addEventListener("keydown", function (evento) {
            if (evento.key === "Escape") cerrar();
        });
    }

    /* --- Dropdown ------------------------------------------------------ */
    function initDropdowns() {
        var dropdowns = document.querySelectorAll("[data-dropdown]");

        dropdowns.forEach(function (dropdown) {
            var trigger = dropdown.querySelector("[data-dropdown-trigger]");
            var menu = dropdown.querySelector("[data-dropdown-menu]");
            if (!trigger || !menu) return;

            function cerrar() {
                menu.hidden = true;
                trigger.setAttribute("aria-expanded", "false");
            }

            function alternar(evento) {
                evento.stopPropagation();
                var abierto = menu.hidden === false;
                document.querySelectorAll("[data-dropdown-menu]").forEach(function (m) {
                    m.hidden = true;
                });
                menu.hidden = abierto;
                trigger.setAttribute("aria-expanded", abierto ? "false" : "true");
            }

            trigger.addEventListener("click", alternar);
            document.addEventListener("click", function (evento) {
                if (!dropdown.contains(evento.target)) cerrar();
            });
            document.addEventListener("keydown", function (evento) {
                if (evento.key === "Escape") cerrar();
            });
        });
    }

    /* --- Modales (envoltura fina sobre <dialog> nativo) ---------------- */
    function initModals() {
        document.querySelectorAll("[data-modal-open]").forEach(function (boton) {
            var destino = document.getElementById(boton.getAttribute("data-modal-open"));
            if (!destino) return;
            boton.addEventListener("click", function () {
                destino.showModal();
                // Un <dialog> cerrado es `display:none` — cualquier
                // textarea auto-ajustable dentro medía `scrollHeight` 0
                // al cargar la página, quedando colapsada hasta que el
                // usuario escribía. Reajustar recién ahora que el modal
                // ya tiene layout real.
                ajustarTextareasEn(destino);
            });
        });

        document.querySelectorAll("dialog.modal").forEach(function (modal) {
            modal.querySelectorAll("[data-modal-close]").forEach(function (boton) {
                boton.addEventListener("click", function () {
                    modal.close();
                });
            });
            // Cerrar al hacer clic sobre el backdrop (fuera del contenido).
            modal.addEventListener("click", function (evento) {
                if (evento.target === modal) modal.close();
            });
        });
    }

    /* --- Tabs (con navegación por teclado, patrón ARIA) ----------------- */
    function initTabs() {
        document.querySelectorAll("[data-tabs]").forEach(function (contenedor) {
            var botones = Array.prototype.slice.call(
                contenedor.querySelectorAll('[role="tab"]')
            );

            function seleccionar(boton) {
                botones.forEach(function (b) {
                    var seleccionado = b === boton;
                    b.setAttribute("aria-selected", seleccionado ? "true" : "false");
                    b.tabIndex = seleccionado ? 0 : -1;
                    var panel = document.getElementById(b.getAttribute("aria-controls"));
                    if (panel) panel.hidden = !seleccionado;
                });
                boton.focus();
            }

            botones.forEach(function (boton, indice) {
                boton.addEventListener("click", function () {
                    seleccionar(boton);
                });
                boton.addEventListener("keydown", function (evento) {
                    var siguiente = null;
                    if (evento.key === "ArrowRight") siguiente = botones[(indice + 1) % botones.length];
                    if (evento.key === "ArrowLeft") siguiente = botones[(indice - 1 + botones.length) % botones.length];
                    if (siguiente) {
                        evento.preventDefault();
                        seleccionar(siguiente);
                    }
                });
            });
        });
    }

    /* --- Textareas auto-ajustables (solo shell SaaS) --------------------
       Django renderiza `rows="10"` por defecto en cualquier Textarea sin
       widget propio (Descripción/Características de Planes, Notas de
       Cuentas bancarias, etc.) — Stitch las muestra compactas y crecen
       solo si el contenido lo requiere. Acotado a `.shell--saas .campo
       textarea` explícitamente: nunca toca los formularios del ERP, que
       comparten la misma clase `.campo` pero no este comportamiento. */
    function ajustarAltura(textarea) {
        textarea.style.height = "auto";
        var maxAltura = parseFloat(getComputedStyle(textarea).maxHeight) || Infinity;
        textarea.style.height = Math.min(textarea.scrollHeight, maxAltura) + "px";
    }

    function ajustarTextareasEn(contenedor) {
        contenedor.querySelectorAll(".campo textarea").forEach(ajustarAltura);
    }

    function initAutoGrowTextareas() {
        document.querySelectorAll(".shell--saas .campo textarea").forEach(function (textarea) {
            textarea.addEventListener("input", function () {
                ajustarAltura(textarea);
            });
            ajustarAltura(textarea);
        });
    }

    /* --- Toasts: auto-cierre + botón de cerrar -------------------------- */
    function initToasts() {
        document.querySelectorAll(".toast").forEach(function (toast) {
            var boton = toast.querySelector(".toast__cerrar");
            var cerrar = function () {
                toast.remove();
            };
            if (boton) boton.addEventListener("click", cerrar);
            window.setTimeout(cerrar, 6000);
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initSidebar();
        initDropdowns();
        initModals();
        initTabs();
        initToasts();
        initAutoGrowTextareas();
    });
})();
