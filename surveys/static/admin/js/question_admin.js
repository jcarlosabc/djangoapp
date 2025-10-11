(function($) {
    $(document).ready(function() {
        const dependsOnSelect = $('#id_depends_on');
        const dependsOnOptionSelect = $('#id_depends_on_option');
        const originalDependsOnOptionValue = dependsOnOptionSelect.val();

        function updateDependsOnOptions(selectedValue) {
            const questionId = selectedValue;
            const currentOptionValue = dependsOnOptionSelect.val();

            if (!questionId) {
                dependsOnOptionSelect.html('<option value="">---------</option>');
                return;
            }

            $.ajax({
                url: '/ajax/get_question_options/',
                data: {
                    'question_id': questionId
                },
                success: function(data) {
                    let options = '<option value="">---------</option>';
                    data.forEach(function(option) {
                        options += '<option value="' + option.id + '">' + option.label + '</option>';
                    });
                    dependsOnOptionSelect.html(options);

                    // Restore selection if possible
                    if (data.some(option => option.id.toString() === originalDependsOnOptionValue)) {
                        dependsOnOptionSelect.val(originalDependsOnOptionValue);
                    } else if (data.some(option => option.id.toString() === currentOptionValue)) {
                        dependsOnOptionSelect.val(currentOptionValue);
                    }
                }
            });
        }

        // Initial load
        if (dependsOnSelect.val()) {
            updateDependsOnOptions(dependsOnSelect.val());
        }

        // Update on change
        dependsOnSelect.on('change', function() {
            updateDependsOnOptions($(this).val());
        });
    });
})(django.jQuery);