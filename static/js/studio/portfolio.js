(function () {
    const MAX_UPLOAD_BYTES = 3.25 * 1024 * 1024;
    const MAX_IMAGE_DIMENSION = 1800;

    function blobFromCanvas(canvas, type, quality) {
        return new Promise(function (resolve) {
            canvas.toBlob(function (result) {
                resolve(result);
            }, type, quality);
        });
    }

    async function compressImageFile(file) {
        if (!file || !file.type || !file.type.startsWith('image/')) {
            return file;
        }

        if (file.size <= MAX_UPLOAD_BYTES) {
            return file;
        }

        const bitmap = await createImageBitmap(file);
        const ratio = Math.min(MAX_IMAGE_DIMENSION / bitmap.width, MAX_IMAGE_DIMENSION / bitmap.height, 1);
        const width = Math.max(1, Math.round(bitmap.width * ratio));
        const height = Math.max(1, Math.round(bitmap.height * ratio));

        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(bitmap, 0, 0, width, height);
        if (typeof bitmap.close === 'function') {
            bitmap.close();
        }

        const outputType = 'image/jpeg';
        const qualities = [0.78, 0.68, 0.58, 0.48];
        let blob = null;
        for (const quality of qualities) {
            blob = await blobFromCanvas(canvas, outputType, quality);
            if (blob && blob.size <= MAX_UPLOAD_BYTES) {
                break;
            }
        }

        if (!blob || blob.size >= file.size) {
            return file;
        }

        const baseName = (file.name || 'portfolio-image').replace(/\.[^.]+$/, '');
        return new File([blob], baseName + '.jpg', { type: outputType, lastModified: Date.now() });
    }

    function updateUploadStatus(form, message) {
        const statusNode = form.querySelector('[data-upload-status]');
        if (statusNode) {
            statusNode.textContent = message;
        }
    }

    async function uploadSingleImage(form, file) {
        const formData = new FormData(form);
        formData.delete('image');
        formData.append('image', file, file.name);

        const response = await fetch(form.action || window.location.href, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        });

        let payload = null;
        try {
            payload = await response.json();
        } catch (_error) {
            payload = null;
        }

        if (!response.ok || (payload && payload.success === false)) {
            const message = payload && payload.message
                ? payload.message
                : 'Upload failed. Please use smaller images and try again.';
            throw new Error(message);
        }
    }

    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    const fileNameNode = document.getElementById('quickUploadFileName');

    if (uploadArea && fileInput) {
        uploadArea.addEventListener('click', function () {
            fileInput.click();
        });

        uploadArea.addEventListener('dragover', function (event) {
            event.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', function () {
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', function (event) {
            event.preventDefault();
            uploadArea.classList.remove('dragover');
            if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length) {
                const dt = new DataTransfer();
                Array.from(event.dataTransfer.files).forEach(function (file) {
                    dt.items.add(file);
                });
                fileInput.files = dt.files;
                if (fileNameNode) {
                    fileNameNode.textContent = fileInput.files.length === 1
                        ? fileInput.files[0].name
                        : fileInput.files.length + ' files selected';
                }
            }
        });

        fileInput.addEventListener('change', function () {
            if (!fileNameNode) {
                return;
            }
            if (fileInput.files && fileInput.files.length) {
                fileNameNode.textContent = fileInput.files.length === 1
                    ? fileInput.files[0].name
                    : fileInput.files.length + ' files selected';
                return;
            }

            fileNameNode.textContent = 'No file selected';
        });
    }

    async function bindCompressionSubmit(formId) {
        const form = document.getElementById(formId);
        if (!form) {
            return;
        }

        form.addEventListener('submit', async function (event) {
            const input = form.querySelector('input[name="image"]');
            if (!input || !input.files || !input.files.length) {
                return;
            }

            event.preventDefault();
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalButtonText = submitBtn ? submitBtn.innerHTML : '';
            if (submitBtn) {
                submitBtn.disabled = true;
            }

            try {
                const files = Array.from(input.files);
                for (let index = 0; index < files.length; index += 1) {
                    updateUploadStatus(form, 'Preparing ' + (index + 1) + ' of ' + files.length + '...');
                    const compressedFile = await compressImageFile(files[index]);
                    if (compressedFile.size > MAX_UPLOAD_BYTES) {
                        throw new Error('One image is still too large after compression. Please choose an image under 3.25 MB.');
                    }

                    updateUploadStatus(form, 'Uploading ' + (index + 1) + ' of ' + files.length + '...');
                    await uploadSingleImage(form, compressedFile);
                }
                updateUploadStatus(form, 'Upload complete. Refreshing gallery...');
                window.location.reload();
            } catch (error) {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalButtonText;
                }
                updateUploadStatus(form, error.message || 'Upload failed. Please try again.');
                alert(error.message || 'Upload failed. Please try again.');
            }
        });
    }

    const searchNode = document.getElementById('gallerySearch');
    const sortNode = document.getElementById('gallerySort');
    const categoryNode = document.getElementById('galleryCategoryFilter');
    const grid = document.getElementById('galleryGrid');
    const emptyFilteredNode = document.getElementById('galleryFilterEmpty');

    function getCards() {
        return Array.from(document.querySelectorAll('.gallery-card'));
    }

    function sortCards(cards) {
        if (!sortNode || !grid) {
            return;
        }

        const mode = sortNode.value;
        cards.sort(function (a, b) {
            const aDate = Number(a.dataset.date || 0);
            const bDate = Number(b.dataset.date || 0);
            const aCaption = (a.dataset.caption || '').toLowerCase();
            const bCaption = (b.dataset.caption || '').toLowerCase();

            if (mode === 'oldest') {
                return aDate - bDate;
            }
            if (mode === 'az') {
                return aCaption.localeCompare(bCaption);
            }
            if (mode === 'za') {
                return bCaption.localeCompare(aCaption);
            }
            return bDate - aDate;
        });

        cards.forEach(function (card) {
            grid.appendChild(card);
        });
    }

    function applyFilters() {
        const cards = getCards();
        const term = (searchNode && searchNode.value || '').trim().toLowerCase();
        const category = (categoryNode && categoryNode.value || 'all').toLowerCase();

        let visible = 0;
        cards.forEach(function (card) {
            const caption = card.dataset.caption || '';
            const tags = card.dataset.tags || '';
            const dateText = card.querySelector('.gallery-card-info small')?.textContent?.toLowerCase() || '';
            const cardCategory = (card.dataset.category || 'other').toLowerCase();

            const matchesTerm = !term || caption.includes(term) || tags.includes(term) || dateText.includes(term);
            const matchesCategory = category === 'all' || cardCategory === category;
            const matches = matchesTerm && matchesCategory;
            card.style.display = matches ? '' : 'none';
            if (matches) {
                visible += 1;
            }
        });

        if (emptyFilteredNode) {
            emptyFilteredNode.classList.toggle('d-none', visible !== 0 || cards.length === 0);
        }
    }

    if (sortNode) {
        sortNode.addEventListener('change', function () {
            const cards = getCards();
            sortCards(cards);
            applyFilters();
        });
    }

    if (searchNode) {
        searchNode.addEventListener('input', applyFilters);
    }

    if (categoryNode) {
        categoryNode.addEventListener('change', applyFilters);
    }

    const layoutButtons = document.querySelectorAll('.layout-switch button[data-layout]');
    layoutButtons.forEach(function (button) {
        button.addEventListener('click', function () {
            if (!grid) {
                return;
            }
            layoutButtons.forEach(function (btn) {
                btn.classList.toggle('active', btn === button);
            });
            const layout = button.dataset.layout;
            grid.classList.toggle('masonry-layout', layout === 'masonry');
        });
    });

    const previewModalNode = document.getElementById('portfolioPreviewModal');
    const previewTitle = document.getElementById('previewTitle');
    const previewImage = document.getElementById('previewImage');
    const previewCaption = document.getElementById('previewCaption');
    const previewDate = document.getElementById('previewDate');
    const previewDimensions = document.getElementById('previewDimensions');
    const previewFileSize = document.getElementById('previewFileSize');
    const previewTags = document.getElementById('previewTags');
    const previewOriginalLink = document.getElementById('previewOriginalLink');

    async function fetchImageSize(url) {
        try {
            const response = await fetch(url);
            if (!response.ok) {
                return null;
            }
            const blob = await response.blob();
            return blob.size;
        } catch (_error) {
            return null;
        }
    }

    function formatBytes(size) {
        if (!size || Number.isNaN(size)) {
            return '--';
        }
        const units = ['B', 'KB', 'MB', 'GB'];
        let value = size;
        let index = 0;
        while (value >= 1024 && index < units.length - 1) {
            value /= 1024;
            index += 1;
        }
        return value.toFixed(index === 0 ? 0 : 2) + ' ' + units[index];
    }

    if (previewModalNode && typeof bootstrap !== 'undefined') {
        const modalInstance = new bootstrap.Modal(previewModalNode);

        document.querySelectorAll('.preview-photo-btn').forEach(function (button) {
            button.addEventListener('click', async function () {
                const caption = button.dataset.caption || 'Portfolio Preview';
                const image = button.dataset.image || '';
                const date = button.dataset.date || '';
                const tags = button.dataset.tags || '';

                if (previewTitle) {
                    previewTitle.textContent = caption;
                }
                if (previewImage) {
                    previewImage.src = image;
                    previewImage.alt = caption;
                }
                if (previewCaption) {
                    previewCaption.textContent = caption;
                }
                if (previewDate) {
                    previewDate.textContent = date;
                }
                if (previewTags) {
                    previewTags.textContent = tags ? 'Tags: ' + tags : 'Tags: --';
                }
                if (previewOriginalLink) {
                    previewOriginalLink.href = image || '#';
                }

                if (previewDimensions) {
                    previewDimensions.textContent = 'Dimensions: loading...';
                }
                if (previewFileSize) {
                    previewFileSize.textContent = 'Original file size: loading...';
                }

                modalInstance.show();

                const tempImage = new Image();
                tempImage.onload = async function () {
                    if (previewDimensions) {
                        previewDimensions.textContent = 'Dimensions: ' + tempImage.naturalWidth + ' x ' + tempImage.naturalHeight + ' px';
                    }
                    const size = await fetchImageSize(image);
                    if (previewFileSize) {
                        previewFileSize.textContent = 'Original file size: ' + formatBytes(size || 0);
                    }
                };
                tempImage.onerror = function () {
                    if (previewDimensions) {
                        previewDimensions.textContent = 'Dimensions: unavailable';
                    }
                    if (previewFileSize) {
                        previewFileSize.textContent = 'Original file size: unavailable';
                    }
                };
                tempImage.src = image;
            });
        });
    }

    bindCompressionSubmit('quickUploadForm');
    bindCompressionSubmit('modalUploadForm');

    const cards = getCards();
    sortCards(cards);
    applyFilters();

    document.querySelectorAll('.portfolio-progress-fill').forEach(function (node) {
        const value = Number(node.dataset.progress || 0);
        node.style.width = Math.max(0, Math.min(100, value)) + '%';
    });
})();
