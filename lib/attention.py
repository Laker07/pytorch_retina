#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jan 28 23:12:05 2019

@author: tony
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jan 23 20:44:06 2019

@author: tony


modified multihaed_attention_3d to 2d from:
https://github.com/zhengyang-wang/3D-Unet--Tensorflow/blob/master/utils/attention.py
"""

import tensorflow as tf
#./from .basic_ops import *
import tensorflow.keras.layers as layers


"""This script defines 3D different multi-head attention layers.
"""

#https://www.tensorflow.org/api_docs/python/tf/layers/conv2d
#basic ops
def Conv2D(inputs, filters, kernel_size, strides, use_bias=False):
    return tf.layers.conv2d(
			inputs=inputs,
			filters=filters,
			kernel_size=kernel_size,
			strides=strides,
			padding='same', #valid
			use_bias=use_bias,
			kernel_initializer=tf.truncated_normal_initializer())
    

def Deconv2D(inputs, filters, kernel_size, strides, use_bias=False):
    """Performs 3D deconvolution without bias and activation function."""

    return tf.layers.conv2d_transpose(
			inputs=inputs,
			filters=filters,
			kernel_size=kernel_size,
			strides=strides,
			padding='same',
			use_bias=use_bias,
			kernel_initializer=tf.truncated_normal_initializer())



def multihead_attention_2d(inputs, total_key_filters, total_value_filters,
							output_filters, num_heads, training, layer_type='SAME',
							name=None):

    """3d Multihead scaled-dot-product attention with input/output transformations.
	
    Args:
		inputs: a Tensor with shape [batch, d, h, w, channels]
		total_key_filters: an integer. Note that queries have the same number 
			of channels as keys
		total_value_filters: an integer
		output_depth: an integer
		num_heads: an integer dividing total_key_filters and total_value_filters
		layer_type: a string, type of this layer -- SAME, DOWN, UP
		name: an optional string
	Returns:
		A Tensor of shape [batch, _d, _h, _w, output_filters]
	
	Raises:
		ValueError: if the total_key_filters or total_value_filters are not divisible
			by the number of attention heads.
    """

    if total_key_filters % num_heads != 0:
        raise ValueError("Key depth (%d) must be divisible by the number of "
						"attention heads (%d)." % (total_key_filters, num_heads))
    if total_value_filters % num_heads != 0:
        raise ValueError("Value depth (%d) must be divisible by the number of "
						"attention heads (%d)." % (total_value_filters, num_heads))
    if layer_type not in ['SAME', 'DOWN', 'UP']:
        raise ValueError("Layer type (%s) must be one of SAME, "
						"DOWN, UP." % (layer_type))

    with tf.variable_scope(name,default_name="multihead_attention_3d",values=[inputs]):
        #produce k,q,v
        q,k,v = compute_qkv_2d(inputs, total_key_filters,total_value_filters, layer_type)
# after splitting, shape is [batch, heads, d, h, w, channels / heads]
        q = split_heads_2d(q, num_heads)
        k = split_heads_2d(k, num_heads)
        v = split_heads_2d(v, num_heads)
        
        print('im at q..',q)
        print('im at k..',k)
        print('im at v..',v)
		# normalize
        key_filters_per_head = total_key_filters // num_heads
        q *= key_filters_per_head**-0.5

		# attention
        x = global_attention_2d(q, k, v, training)
        print('after global att,' , x.shape)
		
        x = combine_heads_2d(x)
        print('after combine, ', x.shape)
        print(x)

        x = Conv2D(x, output_filters, 1,1, use_bias=True)
        print('output ', x.shape)
        return x


def compute_qkv_2d(inputs, total_key_filters, total_value_filters, layer_type):
	"""Computes query, key and value.
	Args:
		inputs: a Tensor with shape [batch, d, h, w, channels]
                                    [batch, h,w,channels]
        
		total_key_filters: an integer
		total_value_filters: and integer
		layer_type: String, type of this layer -- SAME, DOWN, UP
	
	Returns:
		q: [batch, _d, _h, _w, total_key_filters] tensor
		k: [batch, h, w, total_key_filters] tensor
		v: [batch, h, w, total_value_filters] tensor
	"""

	# linear transformation for q
	if layer_type == 'SAME':
		q = Conv2D(inputs, total_key_filters, 1, 1, use_bias=True)
	elif layer_type == 'DOWN':
		q = Conv2D(inputs, total_key_filters, 3, 2, use_bias=True)
	elif layer_type == 'UP':
		q = Deconv2D(inputs, total_key_filters, 3, 2, use_bias=True)

	# linear transformation for k
	k = Conv2D(inputs, total_key_filters, 1, 1, use_bias=True)

	# linear transformation for k
	v = Conv2D(inputs, total_value_filters, 1, 1, use_bias=True)

	return q, k, v


def split_heads_2d(x, num_heads):
	"""Split channels (last dimension) into multiple heads (becomes dimension 1).
	
	Args:
		x: a Tensor with shape [batch, d, h, w, channels]
		num_heads: an integer
	
	Returns:
		a Tensor with shape [batch, num_heads, d, h, w, channels / num_heads]
	"""

	return tf.transpose(split_last_dimension(x, num_heads), [0, 3,1,2,4])


def split_last_dimension(x, n):
	"""Reshape x so that the last dimension becomes two dimensions.
	The first of these two dimensions is n.
	Args:
		x: a Tensor with shape [..., m]
		n: an integer.
	Returns:
		a Tensor with shape [..., n, m/n]
	"""

	old_shape = x.get_shape().dims
	last = old_shape[-1]
	new_shape = old_shape[:-1] + [n] + [last // n if last else None]
	
	ret = tf.reshape(x, tf.concat([tf.shape(x)[:-1], [n, -1]], 0))
	ret.set_shape(new_shape)
	print(ret)
   
	
	return ret


def global_attention_2d(q, k, v, training, name=None):
	"""global self-attention.
	Args:
		q: a Tensor with shape [batch, heads, _d, _h, _w, channels_k]
		k: a Tensor with shape [batch, heads, d, h, w, channels_k]
		v: a Tensor with shape [batch, heads, d, h, w, channels_v]
		name: an optional string
	Returns:
		a Tensor of shape [batch, heads, _d, _h, _w, channels_v]
	"""
	with tf.variable_scope(
			name,
			default_name="global_attention_3d",
			values=[q, k, v]):

		new_shape = tf.concat([tf.shape(q)[0:-1], [v.shape[-1].value]], 0)

		# flatten q,k,v
		q_new = flatten_2d(q)
		k_new = flatten_2d(k)
		v_new = flatten_2d(v)

		# attention
		output = dot_product_attention(q_new, k_new, v_new, bias=None,
					training=training, dropout_rate=0.5, name="global_3d")

		# putting the representations back in the right place
		output = scatter_2d(output, new_shape)

		return output


def reshape_range(tensor, i, j, shape):
	"""Reshapes a tensor between dimensions i and j."""

	target_shape = tf.concat(
			[tf.shape(tensor)[:i], shape, tf.shape(tensor)[j:]],
			axis=0)

	return tf.reshape(tensor, target_shape)


def flatten_2d(x):
	"""flatten x."""

	x_shape = tf.shape(x)
	# [batch, heads, length, channels], length = d*h*w
	x = reshape_range(x, 2, 4, [tf.reduce_prod(x_shape[2:4])])

	return x


def scatter_2d(x, shape):
	"""scatter x."""

	x = tf.reshape(x, shape)

	return x


def dot_product_attention(q, k, v, bias, training, dropout_rate=0.0, name=None):
	"""Dot-product attention.
	Args:
		q: a Tensor with shape [batch, heads, length_q, channels_k]
		k: a Tensor with shape [batch, heads, length_kv, channels_k]
		v: a Tensor with shape [batch, heads, length_kv, channels_v]
		bias: bias Tensor
		dropout_rate: a floating point number
		name: an optional string
	Returns:
		A Tensor with shape [batch, heads, length_q, channels_v]
	"""

	with tf.variable_scope(
			name,
			default_name="dot_product_attention",
			values=[q, k, v]):

		# [batch, num_heads, length_q, length_kv]
		logits = tf.matmul(q, k, transpose_b=True)

		if bias is not None:
			logits += bias

		weights = tf.nn.softmax(logits, name="attention_weights")

		# dropping out the attention links for each of the heads
		weights = tf.layers.dropout(weights, dropout_rate, training)

		return tf.matmul(weights, v)


def combine_heads_2d(x):
	"""Inverse of split_heads_3d.
	Args:
		x: a Tensor with shape [batch, num_heads, d, h, w, channels / num_heads]
	Returns:
		a Tensor with shape [batch, d, h, w, channels]
	"""

	return combine_last_two_dimensions(tf.transpose(x, [0, 2, 3, 1, 4]))


def combine_last_two_dimensions(x):
	"""Reshape x so that the last two dimension become one.
	Args:
		x: a Tensor with shape [..., a, b]
	Returns:
		a Tensor with shape [..., a*b]
	"""

	old_shape = x.get_shape().dims
	a, b = old_shape[-2:]
	new_shape = old_shape[:-2] + [a * b if a and b else None]

	ret = tf.reshape(x, tf.concat([tf.shape(x)[:-2], [-1]], 0))
	ret.set_shape(new_shape)

	return ret
















































