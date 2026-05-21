(function () {
    const selector = "[data-family-pedigree]";
    const rendered = new WeakSet();
    let observer = null;

    function getPedigreeApi() {
        if (window.pedigreejs && window.pedigreejs.pedigreejs) {
            return window.pedigreejs.pedigreejs;
        }
        if (window.pedigreejs && typeof window.pedigreejs.build === "function") {
            return window.pedigreejs;
        }
        return null;
    }

    function getZoomApi() {
        if (window.pedigreejs && window.pedigreejs.pedigreejs_zooming) {
            return window.pedigreejs.pedigreejs_zooming;
        }
        if (window.pedigreejs_zooming) {
            return window.pedigreejs_zooming;
        }
        return null;
    }

    function showMessage(target, message, isError) {
        target.innerHTML = "";
        const node = document.createElement("div");
        node.className = isError ? "family-pedigree-error" : "family-pedigree-placeholder";
        node.textContent = message;
        target.appendChild(node);
    }

    function parseDataset(root) {
        const dataElement = document.getElementById(root.dataset.pedigreeDataId);
        if (!dataElement) {
            return [];
        }
        return JSON.parse(dataElement.textContent || "[]");
    }

    function render(root) {
        if (rendered.has(root)) {
            return;
        }

        const target = document.getElementById(root.dataset.pedigreeTargetId);
        if (!target) {
            return;
        }

        const api = getPedigreeApi();
        if (!api || !window.d3 || !window.jQuery) {
            showMessage(target, "Pedigree renderer is not available.", true);
            rendered.add(root);
            return;
        }

        let dataset = [];
        try {
            dataset = parseDataset(root);
        } catch (error) {
            showMessage(target, "Pedigree data could not be read.", true);
            rendered.add(root);
            return;
        }

        if (!dataset.length) {
            showMessage(target, "No family members available for a pedigree.", false);
            rendered.add(root);
            return;
        }

        target.innerHTML = "";
        const width = Math.max(280, Math.min(root.clientWidth || 520, 640));
        const options = {
            targetDiv: target.id,
            btn_target: `${target.id}-controls`,
            dataset: dataset,
            width: width,
            height: 210,
            symbol_size: 24,
            font_size: "0.68em",
            font_family: "Inter, sans-serif",
            font_weight: 600,
            background: "transparent",
            node_background: "#ffffff",
            store_type: "array",
            edit: false,
            dragNode: false,
            showWidgets: false,
            labels: [],
            diseases: [],
            zoomSrc: [],
            zoomIn: 1,
            zoomOut: 1,
            validate: true,
            DEBUG: false,
            VERBOSE: false,
        };

        try {
            api.build(options);
            rendered.add(root);
            const zoomApi = getZoomApi();
            if (zoomApi && zoomApi.scale_to_fit) {
                window.requestAnimationFrame(function () {
                    zoomApi.scale_to_fit(options);
                });
            }
        } catch (error) {
            console.error("Failed to render pedigree", error);
            showMessage(target, "Pedigree could not be rendered from the current family relationships.", true);
            rendered.add(root);
        }
    }

    function observe(root) {
        if (rendered.has(root)) {
            return;
        }
        if (!("IntersectionObserver" in window)) {
            window.setTimeout(function () {
                render(root);
            }, 0);
            return;
        }
        if (!observer) {
            observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        observer.unobserve(entry.target);
                        render(entry.target);
                    }
                });
            }, { root: null, threshold: 0.01 });
        }
        observer.observe(root);
    }

    function init(root) {
        const scope = root || document;
        if (scope.matches && scope.matches(selector)) {
            observe(scope);
        }
        scope.querySelectorAll(selector).forEach(observe);
    }

    window.RareIndexFamilyPedigree = {
        init: init,
        render: render,
    };

    document.addEventListener("DOMContentLoaded", function () {
        init(document);
    });

    document.body.addEventListener("htmx:afterSwap", function (event) {
        init(event.detail.target);
    });
})();
