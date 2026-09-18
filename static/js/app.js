const form = document.querySelector("[data-detect-form]");

if (form) {
    const fileInput = document.getElementById("pcb-image");
    const modelPathInput = document.getElementById("model-path");
    const chooseModelButton = document.getElementById("choose-model-button");
    const sourcePreview = document.getElementById("source-preview");
    const previewPlaceholder = document.getElementById("preview-placeholder");
    const annotatedPreview = document.getElementById("annotated-preview");
    const resultPlaceholder = document.getElementById("result-placeholder");
    const resultBadge = document.getElementById("result-badge");
    const resultTitle = document.getElementById("result-title");
    const resultMessage = document.getElementById("result-message");
    const summaryGrid = document.getElementById("summary-grid");
    const distributionList = document.getElementById("distribution-list");
    const detailList = document.getElementById("detail-list");
    const exampleName = document.getElementById("example-name");
    const resetButton = document.getElementById("reset-button");
    const exampleButtons = document.querySelectorAll("[data-example-button]");

    const setSummaryCards = (items) => {
        summaryGrid.innerHTML = items.map((item) => `
            <article class="summary-card">
                <span>${item.label}</span>
                <strong>${item.value}</strong>
            </article>
        `).join("");
    };

    const emptyState = () => {
        annotatedPreview.hidden = true;
        annotatedPreview.removeAttribute("src");
        resultPlaceholder.hidden = false;
        resultBadge.textContent = "等待检测";
        resultBadge.style.borderColor = "";
        resultBadge.style.background = "";
        resultBadge.style.color = "";
        resultTitle.textContent = "上传图像后开始识别";
        resultMessage.textContent = "系统将输出风险等级、缺陷统计与坐标明细。";
        setSummaryCards([
            { label: "缺陷总数", value: "-" },
            { label: "主要类别", value: "-" },
            { label: "推理耗时", value: "-" },
            { label: "模型文件", value: "-" },
        ]);
        distributionList.innerHTML = '<p class="empty-copy">检测完成后，这里会显示各缺陷类型的数量和占比。</p>';
        detailList.innerHTML = '<p class="empty-copy">检测完成后，这里会显示每个缺陷的类别、置信度与坐标范围。</p>';
    };

    const setSourcePreview = (src) => {
        sourcePreview.src = src;
        sourcePreview.hidden = false;
        previewPlaceholder.hidden = true;
    };

    const resetSelectionStyles = () => {
        exampleButtons.forEach((button) => button.classList.remove("is-selected"));
    };

    const getDesktopApi = () => {
        if (window.pywebview && window.pywebview.api) {
            return window.pywebview.api;
        }
        return null;
    };

    fileInput.addEventListener("change", () => {
        const file = fileInput.files && fileInput.files[0];
        if (!file) {
            return;
        }
        exampleName.value = "";
        resetSelectionStyles();
        setSourcePreview(URL.createObjectURL(file));
    });

    exampleButtons.forEach((button) => {
        button.addEventListener("click", () => {
            exampleName.value = button.dataset.exampleKey || "";
            fileInput.value = "";
            resetSelectionStyles();
            button.classList.add("is-selected");
            setSourcePreview(button.dataset.examplePreview || "");
        });
    });

    if (chooseModelButton) {
        chooseModelButton.addEventListener("click", async () => {
            const api = getDesktopApi();
            if (!api || typeof api.choose_model !== "function") {
                window.alert("当前环境不支持弹出本地模型选择框，请手动输入 .pt 文件路径。");
                return;
            }

            try {
                const selectedPath = await api.choose_model();
                if (selectedPath) {
                    modelPathInput.value = selectedPath;
                }
            } catch (error) {
                window.alert("模型选择失败，请手动输入模型路径。");
            }
        });
    }

    resetButton.addEventListener("click", () => {
        form.reset();
        modelPathInput.value = modelPathInput.defaultValue;
        exampleName.value = "";
        resetSelectionStyles();
        sourcePreview.hidden = true;
        sourcePreview.removeAttribute("src");
        previewPlaceholder.hidden = false;
        emptyState();
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (!fileInput.files.length && !exampleName.value) {
            window.alert("请先上传 PCB 图像，或先选择一个示例样本。");
            return;
        }

        if (!modelPathInput.value.trim()) {
            window.alert("请先指定模型文件路径。");
            return;
        }

        resultBadge.textContent = "检测中";
        resultTitle.textContent = "正在执行 YOLO 推理";
        resultMessage.textContent = "请稍候，系统正在生成标注结果和缺陷统计。";

        const formData = new FormData(form);

        try {
            const response = await fetch("/api/detect", {
                method: "POST",
                body: formData,
            });

            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.error || data.message || "检测失败");
            }

            const severity = data.level || data.severity;
            const annotatedImage = data.annotated_image || data.annotated_image_url;

            annotatedPreview.src = annotatedImage;
            annotatedPreview.hidden = false;
            resultPlaceholder.hidden = true;

            resultBadge.textContent = severity.label;
            resultBadge.style.borderColor = `${severity.accent}55`;
            resultBadge.style.background = `${severity.accent}22`;
            resultBadge.style.color = severity.accent;
            resultTitle.textContent = `${data.source_name} 检测完成`;
            resultMessage.textContent = severity.message;

            setSummaryCards([
                { label: "缺陷总数", value: data.summary.total },
                { label: "主要类别", value: data.summary.dominant_name },
                { label: "推理耗时", value: `${data.summary.runtime_ms} ms` },
                { label: "模型文件", value: data.summary.model_name },
            ]);

            distributionList.innerHTML = data.summary.distribution.map((item) => `
                <article class="distribution-item">
                    <div class="distribution-head">
                        <strong>${item.name}</strong>
                        <span>${item.count} 个 / ${item.ratio}%</span>
                    </div>
                    <div class="distribution-bar">
                        <span style="width:${item.width}%; background:${item.color};"></span>
                    </div>
                </article>
            `).join("");

            if (!data.details.length) {
                detailList.innerHTML = '<p class="empty-copy">当前图像未检测到明显缺陷。</p>';
                return;
            }

            detailList.innerHTML = data.details.map((item) => `
                <article class="detail-item">
                    <strong>#${item.index} ${item.name}</strong>
                    <div class="detail-meta">
                        <span>置信度 ${item.confidence}%</span>
                        <span>[${item.box[0]}, ${item.box[1]}] -> [${item.box[2]}, ${item.box[3]}]</span>
                    </div>
                </article>
            `).join("");
        } catch (error) {
            emptyState();
            resultBadge.textContent = "检测失败";
            resultTitle.textContent = "推理未完成";
            resultMessage.textContent = error.message || "检测失败，请检查模型路径和图像格式。";
        }
    });

    emptyState();
}
