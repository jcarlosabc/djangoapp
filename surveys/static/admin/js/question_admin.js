
(function($) {
    $(document).ready(function() {
        const dependsOnSelect = $('#id_depends_on');
        const optionFieldRow = $('.field-depends_on_option');
        const minFieldRow = $('.field-depends_on_value_min');
        const maxFieldRow = $('.field-depends_on_value_max');
        const optionSelect = $('#id_depends_on_option');

        const originalOptionValue = optionSelect.val();

        function updateDependencyFields(questionId) {
            if (!questionId) {
                optionFieldRow.hide();
                minFieldRow.hide();
                maxFieldRow.hide();
                return;
            }

            $.ajax({
                url: '/ajax/get_question_dependency_data/',
                data: { 'question_id': questionId },
                success: function(data) {
                    // Hide all by default
                    optionFieldRow.hide();
                    minFieldRow.hide();
                    maxFieldRow.hide();
                    optionSelect.html('<option value="">---------</option>');

                    if (data.qtype === 'single' || data.qtype === 'multi') {
                        let options = '<option value="">---------</option>';
                        data.options.forEach(function(option) {
                            options += '<option value="' + option.id + '">' + option.label + '</option>';
                        });
                        optionSelect.html(options);
                        
                        // Restore selection if possible
                        if (data.options.some(opt => opt.id.toString() === originalOptionValue)) {
                            optionSelect.val(originalOptionValue);
                        }
                        optionFieldRow.show();

                    } else if (data.qtype === 'int' || data.qtype === 'dec') {
                        minFieldRow.show();
                        maxFieldRow.show();
                    }
                },
                error: function() {
                    optionFieldRow.hide();
                    minFieldRow.hide();
                    maxFieldRow.hide();
                }
            });
        }

        // Initial load
        updateDependencyFields(dependsOnSelect.val());

        // Update on change
        dependsOnSelect.on('change', function() {
            updateDependencyFields($(this).val());
        });
    });
})(django.jQuery);
