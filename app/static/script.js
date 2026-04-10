const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const analyzeBtn = document.getElementById('analyze-btn');
const clearBtn = document.getElementById('clear-btn');
const loader = document.getElementById('loader');

let selectedFile = null;

// Drag and drop events
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
});

dropZone.addEventListener('drop', (e) => {
    let dt = e.dataTransfer;
    let files = dt.files;
    handleFiles(files);
});

dropZone.addEventListener('click', () => {
    fileInput.click();
});

fileInput.addEventListener('change', function() {
    handleFiles(this.files);
});

function handleFiles(files) {
    if (files.length > 0) {
        selectedFile = files[0];
        
        // Render preview
        const reader = new FileReader();
        reader.onload = (e) => {
            const oldPreview = dropZone.querySelector('.drop-preview');
            if (oldPreview) oldPreview.remove();
            
            const img = document.createElement('img');
            img.src = e.target.result;
            img.className = 'drop-preview';
            dropZone.appendChild(img);
            
            dropZone.querySelector('i').style.opacity = '0';
            dropZone.querySelector('.drop-text').style.opacity = '0';
            
            analyzeBtn.disabled = false;
        };
        reader.readAsDataURL(selectedFile);
    }
}

clearBtn.addEventListener('click', clearAll);

function clearAll() {
    selectedFile = null;
    fileInput.value = '';
    const preview = dropZone.querySelector('.drop-preview');
    if (preview) preview.remove();
    
    dropZone.querySelector('i').style.opacity = '1';
    dropZone.querySelector('.drop-text').style.opacity = '1';
    analyzeBtn.disabled = true;

    document.getElementById('damage-percent').innerText = "0.00%";
    document.getElementById('mask-area').innerText = "0";
    document.getElementById('image-size').innerText = "- x -";
    
    document.getElementById('empty-state').style.display = 'flex';
    document.getElementById('image-wrapper').style.display = 'none';
    document.getElementById('result-img').src = '';
}

analyzeBtn.addEventListener('click', async () => {
    if (!selectedFile) return;

    loader.classList.add('active');
    
    const scanningTexts = [
        "Grayscale Tensor Conversion...", 
        "U-Net ResNet-34 Feature Extractor...",
        "Decoder Transposed Convolutions...",
        "Binarization Thresholding & Mapping..."
    ];
    let idx = 0;
    const textInterval = setInterval(() => {
        idx = (idx + 1) % scanningTexts.length;
        document.getElementById('loading-text').innerText = scanningTexts[idx];
    }, 600);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const response = await fetch('/predict/', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        clearInterval(textInterval);

        if (response.ok && data.status === 'success') {
            displayResults(data);
        } else {
            alert("运算失败: " + (data.message || "未知错误，请检查后端运行状态。"));
        }
    } catch (err) {
        clearInterval(textInterval);
        console.error(err);
        alert("网络链接中断。请检查 FastAPI 服务器是否运行正常。");
    } finally {
        loader.classList.remove('active');
        document.getElementById('loading-text').innerText = "ResNet-34 Feature Extraction";
    }
});

function animateValue(obj, start, end, duration, formatStr = false) {
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        let current = progress * (end - start) + start;
        if (formatStr) {
            obj.innerHTML = current.toFixed(2) + "%";
        } else {
            obj.innerHTML = Math.floor(current).toLocaleString();
        }
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

function displayResults(data) {
    document.getElementById('empty-state').style.display = 'none';
    const imgWrapper = document.getElementById('image-wrapper');
    imgWrapper.style.display = 'flex';
    
    const resultImg = document.getElementById('result-img');
    resultImg.src = data.output_url + "?t=" + new Date().getTime();

    animateValue(document.getElementById('damage-percent'), 0, data.overall_damage_percent, 1200, true);
    animateValue(document.getElementById('mask-area'), 0, data.mask_area, 1200, false);
    
    document.getElementById('image-size').innerText = `${data.image_width} x ${data.image_height}`;
}
