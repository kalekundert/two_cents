function onAddRow() {
  // Add a row to a formset managed by Django. 
  //
  // This requires two actions: (i) incrementing the TOTAL_FORMS counter and 
  // (ii) adding the new input elements.  The new input elements are copied 
  // from a hidden TEMPLATE_ROW row, given the correct id number, and inserted 
  // just above the template row.  This allows the HTML author to control the 
  // exact content and placement of each row.

  $table = $(this).closest('.budget-table')
  $row = $(this).closest('.budget-row')
  $row_template = $table.find('.budget-row-template')
  prefix = $table.attr('data-prefix')
  $total_forms = $table.find(`#id_${prefix}-TOTAL_FORMS`)

  new_row_id = parseInt($total_forms.attr('value'))
  new_row = $row_template.html().replace(/__prefix__/g, new_row_id)

  $row.after(new_row)
  $total_forms.attr('value', new_row_id + 1)

  // Attach the proper event handlers to the buttons in the new row.
  $new_row = $row.next()
  $new_row.find('.add').on('click', onAddRow)
  $new_row.find('.remove').on('click', onRemoveRow)
}

function onRemoveRow() {
  // Remove a row from a formset managed by Django. 

  // - Grey out all inputs
  // - Replace "remove" button with "restore" button
  // - Implement restore button

  // This requires finding and removing all elements with ids matching the 
  // prefix for the row in question.

  $row = $(this).closest('.budget-row')
  $row.find('input').attr('disabled', 'disabled')
}

function onRestoreRow() {
  $row = $(this).closest('.budget-row')
  $row.find('input').removeAttr('disabled')
  $row.find('removed').hide()
}

function onSubmit() {
  // Update the UI order hidden inputs to match the order the rows appear in.
  // Use direct descendent seletors (">") to avoid selecting the template row.
  ui_order_sele = '.budget-table > .budget-row > [id$="ui_order"]'
  $(this).find(ui_order_sele).each(function(i) {
    $(this).attr('value', i)
  })
}

$(document).ready(function() {
  $('.add').click(onAddRow)
  $('.remove').click(onRemoveRow)
  $('.budget-table').sortable({
    axis: 'y',
    containment: 'parent',
    tolerance: 'pointer',
    cursor: 'grabbing',
    handle: '.drag',
    cancel: '',
  })
  $('#budget-form').submit(onSubmit)
});
